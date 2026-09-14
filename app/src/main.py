import asyncio
import logging
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.agent import opp_to_dict, run_handoff
from src.db import AsyncSessionLocal, get_db
from src.importer import run as run_import
from src.models import Activity, Company, Contact, FairEdition, HandoffRun, Opportunity

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _run_migrations() -> None:
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).parent.parent,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Running Alembic migrations...")
    await asyncio.to_thread(_run_migrations)
    log.info("Migrations done.")
    async with AsyncSessionLocal() as session:
        await run_import(session)
    yield


STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_eur(v) -> str:
    if v is None:
        return "—"
    return f"€{float(v):,.0f}"


def fmt_date(v) -> str:
    if v is None:
        return "—"
    return str(v)


templates.env.filters["eur"] = fmt_eur
templates.env.filters["fmtdate"] = fmt_date


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/companies")


@app.get("/companies", response_class=HTMLResponse)
async def companies(request: Request, q: str = "", page: int = 1, db: AsyncSession = Depends(get_db)):
    page_size = 30
    offset = (page - 1) * page_size

    opp_count_sub = (
        select(Opportunity.company_id, func.count().label("opp_count"))
        .group_by(Opportunity.company_id)
        .subquery()
    )

    stmt = (
        select(Company, func.coalesce(opp_count_sub.c.opp_count, 0).label("opp_count"))
        .outerjoin(opp_count_sub, Company.id == opp_count_sub.c.company_id)
        .order_by(Company.company_name)
    )
    if q:
        stmt = stmt.where(
            or_(
                Company.company_name.ilike(f"%{q}%"),
                Company.region.ilike(f"%{q}%"),
                Company.sales_rep.ilike(f"%{q}%"),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    rows = (await db.execute(stmt.offset(offset).limit(page_size))).all()
    companies_list = [{"company": r.Company, "opp_count": r.opp_count} for r in rows]

    return templates.TemplateResponse("companies.html", {
        "request": request,
        "companies": companies_list,
        "q": q,
        "page": page,
        "total": total,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    })


@app.get("/companies/{company_code}", response_class=HTMLResponse)
async def company_detail(company_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company)
        .options(
            selectinload(Company.contacts),
            selectinload(Company.opportunities).selectinload(Opportunity.fair_edition),
            selectinload(Company.opportunities).selectinload(Opportunity.contact),
        )
        .where(Company.company_code == company_code)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Company not found")

    # Group opportunities by fair name
    fair_groups: dict[str, list] = {}
    for opp in sorted(company.opportunities, key=lambda o: o.opened_on or date.min, reverse=True):
        fair_name = opp.fair_edition.fair_name if opp.fair_edition else "No fair"
        fair_groups.setdefault(fair_name, []).append(opp)

    # Recent company-level activities (not linked to an opportunity)
    acts_result = await db.execute(
        select(Activity)
        .where(Activity.company_id == company.id, Activity.opportunity_id.is_(None))
        .order_by(desc(Activity.occurred_at))
        .limit(20)
    )
    company_activities = acts_result.scalars().all()

    return templates.TemplateResponse("company_detail.html", {
        "request": request,
        "company": company,
        "fair_groups": fair_groups,
        "company_activities": company_activities,
    })


ACTIVITY_PAGE_SIZE = 50


@app.get("/opportunities/{opportunity_code}", response_class=HTMLResponse)
async def opportunity_detail(
    opportunity_code: str,
    request: Request,
    act_page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Opportunity)
        .options(
            selectinload(Opportunity.company),
            selectinload(Opportunity.contact),
            selectinload(Opportunity.fair_edition),
            selectinload(Opportunity.handoff_runs),
        )
        .where(Opportunity.opportunity_code == opportunity_code)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    # Activities paginated — avoid loading thousands of rows at once
    act_offset = (act_page - 1) * ACTIVITY_PAGE_SIZE
    act_count_result = await db.execute(
        select(func.count()).where(Activity.opportunity_id == opp.id)
    )
    act_total = act_count_result.scalar_one()

    acts_result = await db.execute(
        select(Activity)
        .where(Activity.opportunity_id == opp.id)
        .order_by(desc(Activity.occurred_at))
        .offset(act_offset)
        .limit(ACTIVITY_PAGE_SIZE)
    )
    activities = acts_result.scalars().all()

    handoff_runs = sorted(
        opp.handoff_runs,
        key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    height_over = False
    if opp.requested_height_m and opp.fair_edition and opp.fair_edition.max_stand_height_m:
        height_over = float(opp.requested_height_m) > float(opp.fair_edition.max_stand_height_m)

    return templates.TemplateResponse("opportunity.html", {
        "request": request,
        "opp": opp,
        "activities": activities,
        "act_page": act_page,
        "act_total": act_total,
        "act_total_pages": max(1, (act_total + ACTIVITY_PAGE_SIZE - 1) // ACTIVITY_PAGE_SIZE),
        "handoff_runs": handoff_runs,
        "height_over": height_over,
        "today": date.today(),
    })


@app.post("/opportunities/{opportunity_code}/activities")
async def add_activity(
    opportunity_code: str,
    activity_type: str = Form(...),
    details: str = Form(""),
    follow_up_on: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Opportunity).where(Opportunity.opportunity_code == opportunity_code)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(404)

    follow_up_date = None
    if follow_up_on:
        try:
            follow_up_date = date.fromisoformat(follow_up_on)
        except ValueError:
            pass

    act = Activity(
        entry_id=f"user-{uuid.uuid4().hex}",
        company_id=opp.company_id,
        opportunity_id=opp.id,
        activity_type=activity_type,
        occurred_at=datetime.now(timezone.utc),
        details=details or None,
        follow_up_on=follow_up_date,
        completion_marker="N" if activity_type == "task" else None,
        legacy_author="user",
    )
    db.add(act)
    await db.commit()
    return RedirectResponse(f"/opportunities/{opportunity_code}", status_code=303)


@app.post("/opportunities/{opportunity_code}/edit")
async def edit_opportunity(
    opportunity_code: str,
    status: str = Form(""),
    brief_notes: str = Form(""),
    expected_close_on: str = Form(""),
    stand_area_sqm: str = Form(""),
    requested_height_m: str = Form(""),
    client_budget_eur: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Opportunity).where(Opportunity.opportunity_code == opportunity_code)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(404)

    if status:
        opp.status = status.strip().lower()
    opp.brief_notes = brief_notes or None

    if expected_close_on:
        try:
            opp.expected_close_on = date.fromisoformat(expected_close_on)
        except ValueError:
            pass
    else:
        opp.expected_close_on = None

    for field, val in [
        ("stand_area_sqm", stand_area_sqm),
        ("requested_height_m", requested_height_m),
        ("client_budget_eur", client_budget_eur),
    ]:
        if val:
            try:
                setattr(opp, field, Decimal(val.replace(",", ".")))
            except InvalidOperation:
                pass
        else:
            setattr(opp, field, None)

    await db.commit()
    return RedirectResponse(f"/opportunities/{opportunity_code}", status_code=303)


@app.post("/opportunities/{opportunity_code}/handoff")
async def run_handoff_route(opportunity_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Opportunity)
        .options(
            selectinload(Opportunity.company),
            selectinload(Opportunity.contact),
            selectinload(Opportunity.fair_edition),
        )
        .where(Opportunity.opportunity_code == opportunity_code)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(404)

    opp_dict = opp_to_dict(opp)
    preparer_out, checker_out, coord_out, decision, reason = run_handoff(opp_dict)

    run = HandoffRun(
        opportunity_id=opp.id,
        crm_snapshot=opp_dict,
        preparer_output=preparer_out,
        checker_output=checker_out,
        coordinator_decision=decision,
        decision_reason=reason,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return RedirectResponse(f"/handoff-runs/{run.id}", status_code=303)


@app.get("/handoff-runs/{run_id}", response_class=HTMLResponse)
async def handoff_run_detail(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HandoffRun)
        .options(selectinload(HandoffRun.opportunity).selectinload(Opportunity.company))
        .where(HandoffRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404)

    return templates.TemplateResponse("handoff.html", {
        "request": request,
        "run": run,
    })


@app.get("/follow-ups", response_class=HTMLResponse)
async def follow_ups(request: Request, db: AsyncSession = Depends(get_db)):
    today = date.today()
    week_ahead = today + timedelta(days=7)

    result = await db.execute(
        select(Activity)
        .options(
            selectinload(Activity.company),
            selectinload(Activity.opportunity),
        )
        .where(
            Activity.follow_up_on.isnot(None),
            Activity.follow_up_on <= week_ahead,
            or_(Activity.completion_marker == "N", Activity.completion_marker.is_(None)),
        )
        .order_by(Activity.follow_up_on)
        .limit(100)
    )
    activities = result.scalars().all()

    return templates.TemplateResponse("follow_ups.html", {
        "request": request,
        "activities": activities,
        "today": today,
        "week_ahead": week_ahead,
    })


@app.post("/activities/{activity_id}/complete")
async def complete_activity(activity_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(404)
    act.completion_marker = "Y"
    await db.commit()
    return RedirectResponse("/follow-ups", status_code=303)
