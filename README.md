# Exhibition Sales CRM

## Stack and versions

| Component | Version |
|---|---|
| Python | 3.12.7 |
| FastAPI | 0.115.5 |
| SQLAlchemy | 2.0.36 (async) |
| Alembic | 1.14.0 |
| Jinja2 | 3.1.4 |
| asyncpg | 0.30.0 |
| psycopg2-binary | 2.9.10 |
| PostgreSQL | 17.6-alpine3.22 |

## Time spent

Approximately 6 hours.

## Running the app

```bash
./dev.sh      # build + start; imports data on first run; app at http://localhost:3000
./reset.sh    # stop + remove data (next start re-imports)
```

## Import decisions

- **Excluded columns**: `fax`, `legacy_print_layout`, `legacy_row_id` — these are explicitly described as obsolete or non-stable in the data README.
- **`legacy_status`** normalized: stripped of surrounding whitespace and lowercased, so `" open "` and `"Open"` both become `"open"`.
- **Monetary values and measurements**: decimal comma replaced with a decimal point before parsing.
- **Dates** (`DD/MM/YYYY`): parsed with `strptime`. **Date-times** interpreted in `Europe/Rome` and stored as timezone-aware UTC.
- **Empty fields** mapped to `NULL` throughout. Zero is never substituted for an unknown value.
- **Import is idempotent**: the importer checks whether the `companies` table has any rows before proceeding. The first `./dev.sh` after `./reset.sh` runs the full import; subsequent starts skip it.
- **Duplicate codes**: if the same `company_code`, `contact_code`, `opportunity_code`, or `entry_id` appears more than once in the source, only the first occurrence is imported.

## How I handled the team's competing requests

**Sales coordinator vs. account managers — "this year's conversations"**
Activities are imported and created with an `opportunity_id` whenever they belong to a specific opportunity. On the opportunity page the timeline shows only that opportunity's activities, naturally isolating this edition's conversations from previous ones. Company-level activities (not linked to an opportunity) are visible separately on the company page, where account managers can see the full history.

**Sales director vs. technical coordinator — handoff timing**
I chose the **technical coordinator's policy** (conservative): a brief is passed to technical only when the fair edition, client budget, stand area, and requested height are all known *and* the requested height does not exceed the edition's maximum. My reasoning: starting work on a brief that cannot be delivered wastes more time than a short delay to collect the missing details. The sales director's lighter policy (fair + budget only) would be a small change to `BriefChecker.blocking_issues`.

**Follow-ups**
The follow-ups page lists all open activities with a `follow_up_on` date due within the next 7 days (or already overdue), so account managers can see what they're waiting for in one place. Overdue items are highlighted in red.

## The handoff assistant

The assistant is a **deterministic stand-in — no LLM, no API calls, no model downloads**. Every output is labelled `[DETERMINISTIC STAND-IN]` in the UI and code.

Three roles run in sequence in a single process:

1. **BriefPreparer** — collects and structures the CRM and fair data for the opportunity.
2. **BriefChecker** — validates the brief against the handoff policy and returns blocking issues and advisory notes.
3. **Coordinator** — decides `PASS` (no blocking issues) or `STOP` (one or more blocking issues) and records the reason.

Each run is saved to the `handoff_runs` table with the full data snapshot, all role outputs, and the decision. You can re-run the assistant after editing the opportunity; the new run uses the current opportunity data.

### Trying the assistant

**Complete enquiry (→ PASS)**
Find an opportunity where `stand_area_sqm`, `client_budget_eur`, and `requested_height_m` are all set and the requested height does not exceed the edition's `max_stand_height_m`. Click "Prepare handoff brief". The coordinator will decide PASS.

**Incomplete enquiry (→ STOP)**
Find or edit an opportunity with a missing field (e.g., clear the stand area). Click "Prepare handoff brief". The coordinator will decide STOP and list the missing or conflicting items.

## Unfinished work

- Dashboard / pipeline summary (opportunity counts by status, upcoming fair editions)
- Pagination on large activity lists (currently capped at a page limit)
- Editing contact details (contacts are read-only after import)
- Full-text search across activity details
