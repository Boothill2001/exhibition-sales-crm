"""
CSV → PostgreSQL importer.

Runs once at startup when the companies table is empty.
All transformations live here; source files in /data are never modified.

Import decisions:
- fax, legacy_print_layout, legacy_row_id excluded (obsolete per data README)
- legacy_status normalized: strip + lowercase
- Monetary/area/height: decimal comma replaced with point → Decimal
- Dates: DD/MM/YYYY; datetimes stored as UTC (source: Europe/Rome)
- Empty fields → NULL; zero is never substituted for unknown values
- companies_and_contacts.csv is read once; companies and contacts are extracted
  in a single pass to avoid opening the 3.5 MB file twice
"""
import csv
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Activity, Company, Contact, FairEdition, Opportunity

log = logging.getLogger(__name__)

DATA_DIR = Path("/data")
ROME = ZoneInfo("Europe/Rome")
BATCH = 1000


def _str(v: str) -> str | None:
    v = v.strip()
    return v if v else None


def _decimal(v: str) -> Decimal | None:
    v = v.strip().replace(",", ".")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _date(v: str) -> date | None:
    v = v.strip()
    if not v:
        return None
    try:
        return datetime.strptime(v, "%d/%m/%Y").date()
    except ValueError:
        return None


def _datetime_rome(v: str) -> datetime | None:
    v = v.strip()
    if not v:
        return None
    try:
        naive = datetime.strptime(v, "%d/%m/%Y %H:%M")
        return naive.replace(tzinfo=ROME)
    except ValueError:
        return None


def _status(v: str) -> str | None:
    v = v.strip().lower()
    return v if v else None


def _read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


async def already_imported(session: AsyncSession) -> bool:
    result = await session.execute(select(func.count()).select_from(Company))
    return result.scalar_one() > 0


async def run(session: AsyncSession) -> None:
    if await already_imported(session):
        log.info("Import already done, skipping.")
        return

    log.info("Starting data import…")

    # --- 1. Fair editions ---
    fair_editions = []
    for row in _read_csv("fair_editions.csv"):
        fair_editions.append(FairEdition(
            fair_edition_code=row["fair_edition_code"].strip(),
            fair_name=_str(row["fair_name"]) or "",
            city=_str(row["city"]),
            venue=_str(row["venue"]),
            starts_on=_date(row["starts_on"]),
            ends_on=_date(row["ends_on"]),
            max_stand_height_m=_decimal(row["max_stand_height_m"]),
        ))
    session.add_all(fair_editions)
    await session.flush()
    fair_map: dict[str, int] = {fe.fair_edition_code: fe.id for fe in fair_editions}
    log.info(f"  {len(fair_map)} fair editions")

    # --- 2. Companies + contacts — single file read ---
    cc_rows = _read_csv("companies_and_contacts.csv")

    seen_company: dict[str, Company] = {}
    seen_contact: dict[str, Contact] = {}

    for row in cc_rows:
        code = row["company_code"].strip()
        if code not in seen_company:
            seen_company[code] = Company(
                company_code=code,
                company_name=_str(row["company_name"]) or "",
                province_code=_str(row["province_code"]),
                region=_str(row["region"]),
                sales_rep=_str(row["sales_rep"]),
            )

    session.add_all(seen_company.values())
    await session.flush()
    company_map: dict[str, int] = {c.company_code: c.id for c in seen_company.values()}
    log.info(f"  {len(company_map)} companies")

    for row in cc_rows:
        contact_code = row["contact_code"].strip()
        if not contact_code or contact_code in seen_contact:
            continue
        company_id = company_map.get(row["company_code"].strip())
        if not company_id:
            continue
        seen_contact[contact_code] = Contact(
            contact_code=contact_code,
            company_id=company_id,
            first_name=_str(row["contact_first_name"]),
            last_name=_str(row["contact_last_name"]),
            email=_str(row["email"]),
            phone=_str(row["phone"]),
        )

    session.add_all(seen_contact.values())
    await session.flush()
    contact_map: dict[str, int] = {c.contact_code: c.id for c in seen_contact.values()}
    log.info(f"  {len(contact_map)} contacts")

    # --- 3. Opportunities (batched) ---
    seen_opp_codes: set[str] = set()
    opp_batch: list[Opportunity] = []
    opp_map: dict[str, int] = {}

    for row in _read_csv("opportunities.csv"):
        code = row["opportunity_code"].strip()
        if code in seen_opp_codes:
            continue
        seen_opp_codes.add(code)
        company_id = company_map.get(row["company_code"].strip())
        if not company_id:
            continue
        contact_code = row.get("contact_code", "").strip()
        fe_code = row.get("fair_edition_code", "").strip()
        opp_batch.append(Opportunity(
            opportunity_code=code,
            company_id=company_id,
            contact_id=contact_map.get(contact_code) if contact_code else None,
            fair_edition_id=fair_map.get(fe_code) if fe_code else None,
            description=_str(row.get("description", "")),
            amount_eur=_decimal(row.get("amount_eur", "")),
            status=_status(row.get("legacy_status", "")),
            opened_on=_date(row.get("opened_on", "")),
            expected_close_on=_date(row.get("expected_close_on", "")),
            stand_area_sqm=_decimal(row.get("stand_area_sqm", "")),
            client_budget_eur=_decimal(row.get("client_budget_eur", "")),
            requested_height_m=_decimal(row.get("requested_height_m", "")),
            brief_notes=_str(row.get("brief_notes", "")),
            historical_campaign_code=_str(row.get("historical_campaign_code", "")),
        ))
        if len(opp_batch) >= BATCH:
            session.add_all(opp_batch)
            await session.flush()
            for o in opp_batch:
                opp_map[o.opportunity_code] = o.id
            opp_batch.clear()

    if opp_batch:
        session.add_all(opp_batch)
        await session.flush()
        for o in opp_batch:
            opp_map[o.opportunity_code] = o.id

    log.info(f"  {len(opp_map)} opportunities")

    # --- 4. Activity log (batched) ---
    act_batch: list[Activity] = []
    seen_entry: set[str] = set()
    activity_count = 0

    for row in _read_csv("activity_log.csv"):
        entry_id = row["entry_id"].strip()
        if not entry_id or entry_id in seen_entry:
            continue
        seen_entry.add(entry_id)
        company_id = company_map.get(row["company_code"].strip())
        if not company_id:
            continue
        opp_code = row.get("opportunity_code", "").strip()
        act_batch.append(Activity(
            entry_id=entry_id,
            company_id=company_id,
            opportunity_id=opp_map.get(opp_code) if opp_code else None,
            activity_type=_str(row.get("activity_type", "")),
            occurred_at=_datetime_rome(row.get("occurred_at", "")),
            details=_str(row.get("details", "")),
            follow_up_on=_date(row.get("follow_up_on", "")),
            completion_marker=_str(row.get("completion_marker", "")),
            legacy_author=_str(row.get("legacy_author", "")),
        ))
        activity_count += 1
        if len(act_batch) >= BATCH:
            session.add_all(act_batch)
            await session.flush()
            act_batch.clear()

    if act_batch:
        session.add_all(act_batch)
        await session.flush()

    await session.commit()
    log.info(f"  {activity_count} activity log entries")
    log.info("Import complete.")
