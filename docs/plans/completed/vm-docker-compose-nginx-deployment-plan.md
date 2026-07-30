# VM Docker Compose and Nginx Deployment

## Summary

Deploy the current `admin/`, `backend/`, and `R/` applications as three
locally built containers:

```text
Browser → VM:80 → web (Nginx + admin SPA) → api:8000 → Supabase
                                            └──────→ r-service:8000
```

Only Nginx publishes a host port. The deployment is HTTP-only, built from a
known Git commit on the Ubuntu 24.04 x86_64 VM, and relies on OpenStack
security-group rules as the network access boundary.

## Implementation Changes

- Add service-specific Dockerfiles and `.dockerignore` files:

  - `admin`: build with `node:24.13.1-alpine3.23` using `npm ci` and
    `npm run build`; copy only `dist/` into `nginx:1.28.3-alpine3.23`.
    Vite's preview server is not used in production, as recommended by the
    [Vite deployment documentation](https://vite.dev/guide/static-deploy.html).
  - `backend`: use `python:3.14.6-slim-trixie`, install only
    `requirements.txt`, copy `app/`, and run one Uvicorn worker as an
    unprivileged user on port 8000. The one-worker model preserves the
    process-local diagnostic hub.
  - `R`: use `rocker/r-ver:4.6.1`, restore exactly from `renv.lock`, install
    the required Linux build/runtime libraries, and run the existing Plumber
    router on `0.0.0.0:8000` as an unprivileged user. The required Python and
    R base tags are currently published in the
    [Python official image](https://hub.docker.com/_/python) and
    [Rocker image](https://hub.docker.com/r/rocker/r-ver/tags).
  - Exclude `.env`, virtual environments, `node_modules`, build output, local
    R libraries, Git data, caches, and prototype directories from every build
    context.

- Add a root `compose.yaml` with:

  - Services named `web`, `api`, and `r-service`, all using
    `restart: unless-stopped`, bounded JSON-file log rotation, health checks,
    `no-new-privileges`, dropped capabilities, read-only filesystems, and
    temporary writable `/tmp` mounts.
  - `${HTTP_PORT:-80}:8080` published only by `web`; `api` and `r-service` use
    Compose-internal ports only.
  - An edge network shared by `web` and `api`, plus an internal compute
    network shared by `api` and `r-service`. R receives no Supabase or admin
    credentials.
  - Root `.env` injected only into `api`; Compose overrides `R_SERVICE_URL` to
    `http://r-service:8000`.
  - R health checked through `/health`, API through `/health/ready`, and Nginx
    through its local HTTP endpoint. API startup waits for healthy R; Nginx may
    start while API readiness is still unavailable so operational health
    remains observable.
  - No persistent application volumes: durable state remains in Supabase,
    images contain application assets, and diagnostic events remain
    intentionally ephemeral.

- Add a full Nginx configuration that:

  - Serves the admin SPA at `/`, with `try_files` fallback and no-cache
    handling for `index.html`.
  - Caches Vite's hashed `/assets/` files for one year with `immutable`.
  - Proxies `/api/`, `/health/live`, and `/health/ready` to FastAPI while
    preserving `Host`, request ID, and forwarded-address headers.
  - Uses Docker's `127.0.0.11` resolver and a shared upstream zone with
    `server api:8000 resolve`, allowing Nginx to follow API container IP
    changes without reloads. Dynamic `resolve` is supported in open-source
    Nginx from 1.27.3 onward according to the
    [NGINX upstream documentation](https://nginx.org/en/docs/http/ngx_http_upstream_module.html).
  - Disables proxy buffering and caching for the experiment SSE route and
    gives it a read timeout longer than the diagnostic TTL.
  - Sets an approximately 11 MiB request-body limit, bounded
    header/body/upstream timeouts, `server_tokens off`, and basic browser
    security headers. Do not add HSTS because this deployment is HTTP-only.
  - Returns `404` for `/test/*`, `/docs`, `/redoc`, and `/openapi.json`; the
    player and public API documentation are not deployed through Nginx in this
    phase.
  - Requires no CORS configuration because the SPA and API remain
    same-origin.

## Deployment and Operations

- On the VM, check out an exact release commit, create the ignored `.env` with
  Supabase credentials and a strong `ADMIN_ACCESS_KEY`, restrict it to the
  deployment user with mode `0600`, and run:

  1. `docker compose config`
  2. `docker compose build --pull`
  3. `docker compose up -d --remove-orphans`
  4. `docker compose ps`
  5. Smoke tests against `http://<VM-IP>/`

- Updates use the same sequence after checking out the next known commit.
  Rollback checks out the previous commit and rebuilds/recreates the services;
  there is no local database migration or volume rollback.
- Keep logs on stdout/stderr and inspect them with `docker compose logs`.
  Docker log rotation prevents unbounded VM disk consumption.
- README expansion, TLS/domain setup, automated CI/registry delivery, and the
  future test-player route remain deferred to their later phases.

## Test Plan

- Before image builds, run the existing R test suite, backend tests plus
  `python -m pyright`, and admin tests plus `npm run lint` and
  `npm run build`.
- Validate `docker compose config`, build all images from clean contexts, and
  run `nginx -t` inside the web image.
- Confirm:

  - `/` serves the admin application.
  - `/health/live` returns `200`; `/health/ready` returns `200` only when both
    Supabase and R are ready.
  - An unauthenticated admin request returns `401`, while the configured key
    unlocks the dashboard.
  - SSE diagnostics arrive incrementally without buffering during a complete
    admin simulation.
  - `/test/*` and FastAPI documentation routes return `404`.
  - `docker compose ps` shows only the web service with a published port.
  - Supabase and admin secrets are absent from the web and R environments.
  - Restarting or recreating `api` and `r-service` restores readiness without
    restarting Nginx; Supabase-backed assessment state survives while
    process-local diagnostics are cleared.

## Assumptions

- The VM already has working Docker Engine and Docker Compose and can fetch
  base images and R/Python/npm dependencies.
- OpenStack security-group rules restrict port 80 to trusted source addresses.
  `ADMIN_ACCESS_KEY` protects admin endpoints, but the current OR/player API
  routes are permissive and the key itself travels unencrypted over HTTP.
- This is a controlled, single-process experimentation deployment, not the
  externally reachable student pilot. JWT authorization, HTTPS, rate
  limiting, test-player deployment, multi-worker scaling, and concurrency
  tuning remain out of scope.
- Only `admin/` is built as the web application; the existing `frontend/` and
  protected prototype directories are not included or modified.
