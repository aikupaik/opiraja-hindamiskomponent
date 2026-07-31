# Task 7 Dockerfile Change Log

Date started: 2026-07-31

## Project changes

- `admin/Dockerfile` keeps the multi-stage, unprivileged HTTP-only Nginx
  runtime on port 8080 and now validates its configuration during the build.
- `backend/Dockerfile` keeps Uvicorn on HTTP port 8000 and adds the explicit
  `--proxy-headers` flag. Its trusted proxy CIDR remains supplied by the
  Compose `FORWARDED_ALLOW_IPS` environment value.
- `R/Dockerfile` was not changed; R remains HTTP-only on the internal
  `compute` network.

## VM deployment status

The API image was rebuilt and the API container was recreated with the
following inspected command suffix: `--workers 1 --proxy-headers`. Its
runtime environment contains `FORWARDED_ALLOW_IPS=172.30.0.0/24`. All API, R,
and web health checks are green. No certificate tooling, certificate/key
files, TLS volume, or port 443 publication was added to any image.

## Repository validation

- Admin Vitest: 11 tests passed.
- Admin Oxlint: passed.
- Admin TypeScript/Vite build: passed.
- Backend Pyright: `0 errors, 0 warnings, 0 informations`.
- Backend pytest under the project-declared Python 3.14.6 API image: 88 passed,
  1 opt-in R-contract test skipped.
- The local Python 3.12.3 environment's pytest run stalled on its first async
  admin test; no Python source was changed for tasks 5–7. The Python 3.14
  container run is the authoritative suite result for this deployment.
