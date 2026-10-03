# Alfy Work Intelligence: implementation guide

A local personal work-record system that turns notes, documents, and read-only Git evidence into searchable work history and grounded reports.

## Scope

**Repository role:** Local application.

The single-user local model is intentional. Ollama is optional; report claims must remain traceable to captured evidence.

## Local evaluation

Follow the existing root README for Python backend configuration and the local SQLite data path. The frontend is a separate Vite application:

```sh
cd frontend
npm ci
npm run dev
```

Run the Python backend in a separate terminal using its documented virtual environment and requirements. A running frontend alone is not a working evidence/report service. Ollama is optional; verify evidence-only operation first.

## Code map

| Path | Responsibility |
| --- | --- |
| `backend` | Backend service and persistence boundary |
| `frontend` | Browser UI application |

## Configuration

`.env.example`: `ALFY_DATA_DIR`, `ALFY_BACKEND_HOST`, `ALFY_BACKEND_PORT`, `ALFY_OLLAMA_URL`, `VITE_API_BASE`

Example files document variable names, not production values. Keep credentials and operator keys outside Git.

## Walkthrough

Capture a work note, inspect extracted items, link evidence, search the history, and generate an evidence-only report.

## Verification

From `frontend`: `npm run build`.

These are evaluation commands, not a claim that all checks passed. See the pull request validation for checks actually executed in this maintenance pass.

## Evidence for a case study

Describe this repository as a **local application**. A useful case study explains the problem above, traces the walkthrough to its source, names a concrete implementation decision, and records a repeatable evaluation. Separate implemented behavior from roadmap work. Capture screenshots using synthetic data and identify the demonstrated commit.
