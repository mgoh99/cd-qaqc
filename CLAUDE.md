# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

CD QAQC Tracker is a Flask dashboard for Clearspace's construction documents QA/QC review process. It pulls live project data from Wrike (project management platform) and displays milestones, timelines, and review statuses in a Gantt chart and table view.

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env   # add WRIKE_TOKEN and FLASK_SECRET_KEY
python api/index.py    # runs at http://localhost:5055
```

No test suite — verify manually by loading the dashboard and confirming data appears without a 503 error.

## Environment Variables

| Variable | Purpose |
|---|---|
| `WRIKE_TOKEN` | Wrike API Bearer token |
| `FLASK_SECRET_KEY` | Flask session encryption |

## Architecture

**Entry point:** `api/index.py` — single Flask route (`/`) that calls `build_qaqc_projects()`, computes date-based status fields, builds Gantt JSON, and renders the dashboard template. Deployed as a Vercel serverless Python function (`vercel.json`).

**Data layer:** `services/wrike_client.py` — all Wrike API logic lives here. `build_qaqc_projects()` is the main function; it fetches child projects from the B-Design folder (`IEAFNYJDI44OSHOZ`), resolves custom fields (PM, designer, CAD tech, etc.) and task milestone dates, then returns two lists: projects with a Technical Designer assigned, and those without.

**Templates:** `templates/qaqc.html` contains the Gantt chart (Chart.js) and both project tables. Checkbox state (QAQC completion) persists in `localStorage` under key `qaqc_completed_v1` — no server-side state.

## Key Wrike Concepts

- Projects are child folders under the B-Design folder
- Custom fields on folders carry project metadata (PM, sqft, designer roles, etc.)
- Milestone dates come from tasks within each project folder, matched by name (e.g. "Draft CD 80%", "Permit Submission")
- Contact IDs are resolved to names via the contacts endpoint

## Deployment

Deployed on Vercel. `vercel.json` routes all traffic to `api/index.py` and serves `/static/` directly. To deploy:

```bash
vercel deploy         # preview
vercel deploy --prod  # production
```
