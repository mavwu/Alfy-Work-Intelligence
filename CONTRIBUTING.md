# Contributing

Thank you for your interest in Alfy Work Intelligence.

## Before opening a change

- Search existing issues and pull requests to avoid duplicate work.
- Use an issue to discuss substantial features or behavioral changes before implementation.
- Never include real work records, database files, exports, access tokens, or personal filesystem paths in an issue or pull request.

## Development setup

On Windows, run `setup.bat` from the repository root. The manual setup is:

```text
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
```

Copy `.env.example` to `.env` for local overrides. The `.env` file and application data are intentionally excluded from Git.

## Required checks

Run these checks before submitting a pull request:

```text
.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```

Pull requests should explain the user-visible outcome, call out data-model or migration changes, and include the checks performed. Add or update tests when behavior changes.

## Scope and design principles

Keep the application local-first, single-user, evidence-grounded, and usable without an AI model. Avoid changes that transmit private work data to external services without an explicit, documented user action.
