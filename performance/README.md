# Performance harness

This directory is the repository-owned harness for the pre-launch capacity and
stress-testing plan. It is intentionally separate from application code and
does not change public APIs, response types, or the database schema.

## Current foundation

The initial foundation provides:

- a pinned `grafana/k6:1.5.0` runner reference;
- a loopback-only Compose overlay for the real API, R, and isolated API-only
  performance service;
- a non-authenticated static-edge smoke script; and
- deterministic R-only and API-only component scripts; and
- runbook, report, fixture, and result conventions.

It does **not** contain a pilot endpoint, credentials, player tokens, service
keys, database seed data, or database cleanup implementation. API-only fixture
state exists only inside a fresh performance container and disappears when
that container is removed.

## Prerequisites

The remote load-generator machine needs either:

1. a native k6 1.5.x binary on `PATH`; or
2. Docker access, which pulls the pinned `grafana/k6:1.5.0` image on first use.

The harness uses HTTP-level k6 scripts, so it does not need a browser build or
Chromium. Do not install or run k6 on the pilot VM for public-load tests: the
generator must be a separate approved machine.

Docker runners are supported on a rootful Linux host and on Docker Desktop for
macOS 4.34 or newer. The R-only SSH-tunnel commands require
[host networking](https://docs.docker.com/engine/network/drivers/host/). On
macOS, enable **Settings > Resources > Network > Host networking**, use Linux
containers, and leave Enhanced Container Isolation disabled; Docker Desktop
does not support host networking with that isolation mode. Verify the tunneled
health endpoint from inside a host-networked container before running k6.

The generator is part of the measured environment. Record its hardware, OS,
Docker Desktop/client/engine versions, Docker VM CPU and memory allocation, and
the immutable k6 image digest during preflight. Capture generator CPU, memory,
and network samples during every non-smoke run. Keep one generator and runner
configuration for a comparison matrix; results from a different generator or
runner configuration form a new matrix and require a new baseline.

## Layout

| Path | Purpose |
| --- | --- |
| `compose.loopback.yaml` | Exposes component ports on VM loopback and defines the isolated `api-perf` service. |
| `bin/monitor-vm.sh` | Captures VM samples and live Docker/Nginx evidence for one run. |
| `k6/static-edge-smoke.js` | One-client public static-edge smoke check. |
| `k6/r-only.js` | Replays the internal R v2 `model` -> `select` -> `advance` flow in smoke, closed-VU, or open arrival-rate mode. |
| `k6/api-only.js` | Runs bounded route ceilings or complete stateful sessions against one fake-backed Uvicorn worker. |
| `fixtures/` | Version-controlled, non-secret graph and R request fixtures. |
| `preflight.md` | Generator, VM, and Supabase preflight worksheet with safe collection commands. |
| `results/` | Ignored per-run evidence output. |
| `runbook.md` | Operational sequence, safety gates, and abort procedure. |
| `report-template.md` | Required evidence and conclusion structure for each run. |

## Runner convention

All future commands must use the exact k6 image tag above or a documented
native 1.5.x installation. Record the resolved image ID and repository digest,
not only the mutable tag. A scenario receives its non-secret configuration
through protected environment input; secrets are never written into this
directory, a command line, k6 output, or a report.

The public endpoint and certificate fingerprint are supplied only after the
preflight stage has approved them. Until then, the smoke script remains a
checked-in template and must not be run with a guessed target.

## API-only image boundary

`backend/Dockerfile.performance` derives from the exact local production API
image and adds only the performance app, concurrency-safe test repository, and
committed graph fixtures. The normal backend Dockerfile does not copy that
code. The derived service uses a separate Compose network and loopback port
`18002`, so public Nginx cannot route to it. Its FastAPI lifespan exports only
aggregate synthetic-state and event-loop evidence on graceful shutdown.
