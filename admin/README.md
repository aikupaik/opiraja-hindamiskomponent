# Assessment Lab admin dashboard

The `admin` project is the operator-facing React/Vite application for source
management, item-bank auditing, and manual assessment simulation.

It uses plain React state, CSS, and hash navigation:

- `#/materials` manages source materials and stored YG rules;
- `#/items` audits and revises exact-course item inventory; and
- `#/simulation` drives the existing OR/player API with scoped diagnostics.

## Local development

First start FastAPI on port `8001`:

```sh
cd backend
source .venv/bin/activate
uvicorn app.main:create_app --factory --reload --port 8001 --env-file ../.env
```

Configure `ADMIN_ACCESS_KEY` only in the backend `.env`. Never create a Vite
environment variable containing it. Start the dashboard:

```sh
cd admin
npm install
npm run dev
```

Vite proxies same-origin `/api` requests to `http://127.0.0.1:8001`, so broad
CORS is not required. The operator enters the key on the unlock screen; after
FastAPI validates `/api/v1/admin/session`, it is kept only in
`sessionStorage`. Locking removes it.

## Verification

```sh
npm test
npm run lint
npm run build
```

The simulation page opens authenticated SSE with `fetch`, creates a unique
experiment ID, uses the production test/player routes, honors `Retry-After`,
and lets the operator submit each answer manually. Cancel and page cleanup
abort pending requests, polling, and event streams.

Experiment diagnostics are bounded, process-local, and ephemeral. They do not
survive a backend restart, expire after 60 minutes by default, and are
intended for the current single-process experimentation environment.
