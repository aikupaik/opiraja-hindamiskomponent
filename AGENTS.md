# AGENTS.md

## Project objective

Transform the existing prototype into a maintainable full-stack application
according to `pilot_architecture_plan.md`.

The prototype demonstrates intended behaviour but is not authoritative for
architecture, security, validation, persistence, or production quality.

# Python project instructions

Use the project's `backend/.venv` virtual environment.

After creating or modifying Python code, run:

    python -m pyright

Do not finish the task while Pyright reports errors.

Fix type errors properly. Do not add `# type: ignore` or change the
Pyright configuration unless I explicitly request it.

# React project instructions

After creating or modifying Typescript code, run:

    npm run lint

Do not finish the task while Oxlint reports errors.

Fix type errors properly.