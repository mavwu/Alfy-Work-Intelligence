# Alfy Work Intelligence

Alfy Work Intelligence is a local-first personal work intelligence system for Ride Yanga engineering work. It captures messy work notes, imports historical reports, scans local Git repositories read-only, stores evidence in SQLite, and helps generate grounded updates, reports, reflections, and exports.

The V1 app is intentionally single-user and local. There are no cloud accounts, hosted databases, subscriptions, teams, employee monitoring, screenshots, keylogging, or automatic remote AI calls.

## What V1 Does

- Creates one default workspace: `Ride Yanga`, for user `Alfy`.
- Saves raw work logs exactly as entered.
- Extracts reviewable structured work items from messy notes.
- Supports Evidence Only Mode when Ollama is unavailable.
- Connects to local Ollama when available and lets you select an installed model.
- Registers multiple local Git repositories with roles:
  - `USER_APP`
  - `DRIVER_APP`
  - `DASHBOARD_API`
  - `WORKING_SANDBOX`
  - `OTHER`
- Links a working sandbox repository to a canonical repository, such as Working Repo promoting to Dashboard / API.
- Scans Git commit metadata and working tree status without modifying repositories.
- Stores evidence from user logs, Git commits, working tree status, and imported documents.
- Uses conservative duplicate/promotion detection for sandbox-to-canonical work.
- Imports `.docx`, `.pdf`, `.md`, and `.txt` documents.
- Uses SQLite FTS5 for local search and work-memory retrieval.
- Generates draft reports from confirmed evidence.
- Exports reports to DOCX and PPTX.
- Provides a grounded work-history chat area.

## Project Structure

```text
backend/
  app/
    routers/       FastAPI route groups
    services/      AI, Git scanning, FTS, import, report, chat logic
    models.py      SQLAlchemy schema
    db.py          SQLite initialization and FTS5 setup
  tests/
frontend/
  src/
run.bat
setup.bat
.env.example
```

## First-Time Setup on Windows

Install these first:

1. Python 3.11 or newer
2. Node.js 20 or newer
3. Git
4. Optional: Ollama, with at least one local model already installed

Then run:

```bat
setup.bat
```

That creates `.venv`, installs backend dependencies, and runs `npm install` in `frontend/`.

If Python currently opens the Microsoft Store instead of running normally, install Python from python.org and make sure `python --version` works in a new Command Prompt.

## Normal Startup on Windows

After setup, run:

```bat
run.bat
```

It starts:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

Open the frontend URL in your browser.

## Data Location

By default, local data is stored at:

```text
%USERPROFILE%\.alfy-work-intelligence
```

You can change it in `.env`:

```text
ALFY_DATA_DIR=D:\AlfyWorkData
```

Do not store the data directory inside `frontend/`.

## Ollama

The app checks:

```text
http://127.0.0.1:11434
```

If Ollama is unavailable, the app continues in Evidence Only Mode. You can still log work, scan Git repositories, import files, search, view the timeline, review evidence, and generate deterministic drafts.

The app does not download models automatically.

## Core Workflow

1. Complete onboarding.
2. Register Ride Yanga repositories.
3. Link Working Repo to Dashboard / API if it promotes tested changes there.
4. Import historical reports and summaries.
5. Use Log Work for quick messy notes or pasted Codex/ChatGPT summaries.
6. Review inferred work items.
7. Confirm valid work.
8. Scan repositories.
9. Ask work-history questions in Chat.
10. Generate a report draft.
11. Review and approve it.
12. Export DOCX or PPTX.

## Running Tests

```bat
.venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend build check:

```bat
cd frontend
npm run build
```

## Implemented API Areas

- `/api/workspaces`
- `/api/repositories`
- `/api/git`
- `/api/work-logs`
- `/api/work-items`
- `/api/evidence`
- `/api/imports`
- `/api/timeline`
- `/api/reports`
- `/api/chat`
- `/api/ai`
- `/api/settings`
- `/api/dashboard`

## Important V1 Design Notes

- Raw notes are preserved.
- Inferred work must be reviewed before it appears as confirmed work.
- Official reports use confirmed work by default.
- Low-confidence evidence is not silently turned into accomplishments.
- Git scanning is read-only.
- Large/generated dependency folders are ignored during Git scanning.
- AI prompts are separated by task area instead of using one universal prompt.
- Ollama is the only implemented AI provider in V1.

## Deferred or Incomplete Features

- No remote AI providers are implemented.
- No GitHub API integration.
- No autonomous web browsing.
- No authentication or multi-user support.
- No advanced vector search; V1 uses SQLite FTS5.
- AI duplicate detection is conservative and heuristic-assisted; uncertain matches are marked for review rather than auto-merged.
- Report style profiling is initialized and stored, but advanced style-example retrieval is intentionally minimal in V1.
- Background jobs are lightweight in-process jobs, not a durable queue.
- The UI supports editing generated report drafts, but inline editing of every extracted work item field is basic.

## Verification Performed

- Backend tests: passing.
- Frontend production build: passing.
- Backend startup smoke test: passing.
- Frontend Vite startup smoke test: passing.
- Core workflow smoke test: work log -> confirm work item -> generate weekly report -> export DOCX.
