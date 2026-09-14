"""
Handoff assistant — deterministic stand-in (no LLM, no API calls).

Three roles run in sequence in a single process:
  BriefPreparer  — collects and structures the CRM and fair data
  BriefChecker   — validates the brief against the handoff policy
  Coordinator    — decides PASS or STOP and records the reason

The handoff policy applied is the technical coordinator's (conservative):
  a brief is passed only when the fair edition, customer budget, stand area,
  and requested height are all known and the height is within the edition limit.

This is labelled [DETERMINISTIC STAND-IN] throughout to distinguish it from
real model output.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any


def _json_safe(v: Any) -> Any:
    """Convert Decimal → str so the dict is JSON-serializable."""
    if isinstance(v, Decimal):
        return str(v)
    return v

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role 1: BriefPreparer
# ---------------------------------------------------------------------------

def brief_preparer(opp: dict[str, Any]) -> dict[str, Any]:
    """[DETERMINISTIC STAND-IN] Collects and structures the handoff brief."""
    fair = opp.get("fair_edition") or {}
    contact = opp.get("contact") or {}
    company = opp.get("company") or {}

    brief = {
        "_role": "BriefPreparer",
        "_label": "[DETERMINISTIC STAND-IN]",
        "company_name": company.get("company_name"),
        "contact_name": _full_name(contact),
        "opportunity_code": opp.get("opportunity_code"),
        "description": opp.get("description"),
        "status": opp.get("status"),
        "fair_name": fair.get("fair_name"),
        "fair_edition_code": fair.get("fair_edition_code"),
        "fair_city": fair.get("city"),
        "fair_venue": fair.get("venue"),
        "fair_starts_on": _fmt_date(fair.get("starts_on")),
        "fair_ends_on": _fmt_date(fair.get("ends_on")),
        "max_stand_height_m": _fmt_decimal(fair.get("max_stand_height_m")),
        "client_budget_eur": _fmt_decimal(opp.get("client_budget_eur")),
        "stand_area_sqm": _fmt_decimal(opp.get("stand_area_sqm")),
        "requested_height_m": _fmt_decimal(opp.get("requested_height_m")),
        "brief_notes": opp.get("brief_notes"),
        "expected_close_on": _fmt_date(opp.get("expected_close_on")),
        "proposed_next_step": _propose_next_step(opp, fair),
    }
    return brief


def _full_name(contact: dict) -> str | None:
    parts = [contact.get("first_name"), contact.get("last_name")]
    name = " ".join(p for p in parts if p)
    return name or None


def _fmt_date(d: Any) -> str | None:
    if d is None:
        return None
    return str(d)


def _fmt_decimal(d: Any) -> str | None:
    if d is None:
        return None
    return str(d)


def _propose_next_step(opp: dict, fair: dict) -> str:
    """[DETERMINISTIC STAND-IN] Rule-based next-step proposal."""
    missing = _find_missing(opp, fair)
    if not missing:
        return (
            "All required information is present. Proposed next step: "
            "pass the brief to the technical team for stand design review."
        )
    return (
        f"The following information is still missing: {', '.join(missing)}. "
        "Proposed next step: contact the customer to obtain the outstanding details "
        "before handing off to technical."
    )


# ---------------------------------------------------------------------------
# Role 2: BriefChecker
# ---------------------------------------------------------------------------

def brief_checker(brief: dict[str, Any], opp: dict[str, Any]) -> dict[str, Any]:
    """[DETERMINISTIC STAND-IN] Validates the brief against the handoff policy."""
    fair = opp.get("fair_edition") or {}
    issues = []

    if not brief.get("fair_edition_code"):
        issues.append("Fair edition is not set.")

    budget = opp.get("client_budget_eur")
    if budget is None:
        issues.append("Customer budget (client_budget_eur) is unknown.")

    area = opp.get("stand_area_sqm")
    if area is None:
        issues.append("Stand area (stand_area_sqm) is unknown.")

    height = opp.get("requested_height_m")
    if height is None:
        issues.append("Requested height is unknown.")

    max_height = fair.get("max_stand_height_m")
    if height is not None and max_height is not None:
        h = Decimal(str(height))
        mh = Decimal(str(max_height))
        if h > mh:
            issues.append(
                f"Requested height ({h} m) exceeds the edition maximum ({mh} m)."
            )

    # Advisory checks (do not block, but flag)
    advisory = []
    if not opp.get("contact_id"):
        advisory.append("No primary contact linked to this opportunity.")
    if not opp.get("expected_close_on"):
        advisory.append("Expected close date is not set.")

    return {
        "_role": "BriefChecker",
        "_label": "[DETERMINISTIC STAND-IN]",
        "blocking_issues": issues,
        "advisory_notes": advisory,
        "policy": "technical-conservative",
    }


def _find_missing(opp: dict, fair: dict) -> list[str]:
    missing = []
    if not opp.get("fair_edition"):
        missing.append("fair edition")
    if opp.get("client_budget_eur") is None:
        missing.append("client budget")
    if opp.get("stand_area_sqm") is None:
        missing.append("stand area")
    if opp.get("requested_height_m") is None:
        missing.append("requested height")
    return missing


# ---------------------------------------------------------------------------
# Role 3: Coordinator
# ---------------------------------------------------------------------------

def coordinator(brief: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    """[DETERMINISTIC STAND-IN] Decides whether to pass or stop the handoff."""
    blocking = check.get("blocking_issues", [])

    if blocking:
        decision = "STOP"
        reason = "Cannot hand off: " + " | ".join(blocking)
    else:
        decision = "PASS"
        reason = (
            "All required fields are present and within limits. "
            "Brief is ready to pass to the technical team."
        )

    return {
        "_role": "Coordinator",
        "_label": "[DETERMINISTIC STAND-IN]",
        "decision": decision,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------

def run_handoff(opp_dict: dict[str, Any]) -> tuple[dict, dict, dict, str, str]:
    """
    Run the three-role handoff pipeline.
    Returns (preparer_output, checker_output, coordinator_output, decision, reason).
    """
    log.info(f"Running handoff agent for opportunity {opp_dict.get('opportunity_code')}")

    preparer_out = brief_preparer(opp_dict)
    checker_out = brief_checker(preparer_out, opp_dict)
    coord_out = coordinator(preparer_out, checker_out)

    return (
        preparer_out,
        checker_out,
        coord_out,
        coord_out["decision"],
        coord_out["reason"],
    )


def opp_to_dict(opp: Any) -> dict[str, Any]:
    """Serialize an Opportunity ORM object to a plain dict for the agent.

    All Decimal values are converted to str so the dict is safe for JSON storage.
    """
    fair = opp.fair_edition
    contact = opp.contact
    company = opp.company

    return {
        "opportunity_code": opp.opportunity_code,
        "description": opp.description,
        "status": opp.status,
        "amount_eur": _json_safe(opp.amount_eur),
        "client_budget_eur": _json_safe(opp.client_budget_eur),
        "stand_area_sqm": _json_safe(opp.stand_area_sqm),
        "requested_height_m": _json_safe(opp.requested_height_m),
        "brief_notes": opp.brief_notes,
        "expected_close_on": str(opp.expected_close_on) if opp.expected_close_on else None,
        "contact_id": opp.contact_id,
        "fair_edition": {
            "fair_edition_code": fair.fair_edition_code,
            "fair_name": fair.fair_name,
            "city": fair.city,
            "venue": fair.venue,
            "starts_on": str(fair.starts_on) if fair.starts_on else None,
            "ends_on": str(fair.ends_on) if fair.ends_on else None,
            "max_stand_height_m": _json_safe(fair.max_stand_height_m),
        } if fair else None,
        "contact": {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "email": contact.email,
            "phone": contact.phone,
        } if contact else None,
        "company": {
            "company_name": company.company_name,
            "company_code": company.company_code,
        } if company else None,
    }
