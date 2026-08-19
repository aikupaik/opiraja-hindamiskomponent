# Performance harness

This directory is the repository-owned harness for the pre-launch capacity and
stress-testing plan. It is intentionally separate from application code and
does not change public APIs, response types, or the database schema.

## Current foundation

The initial foundation provides:

- a pinned `grafana/k6:1.5.0` runner reference;
- a loopback-only Compose overlay for the API and R component-test endpoints;
- a non-authenticated static-edge smoke script; and
- runbook, report, fixture, and result conventions.

It does **not** contain a pilot endpoint, credentials, player tokens, service
keys, seed data, or cleanup implementation. Those are added only in the
subsequent fixture and scenario steps.

## Prerequisites

The remote load-generator machine needs either:

1. a native k6 1.5.x binary on `PATH`; or
2. Docker access, which pulls the pinned `grafana/k6:1.5.0` image on first use.

The harness uses HTTP-level k6 scripts, so it does not need a browser build or
Chromium. Do not install or run k6 on the pilot VM for public-load tests: the
generator must be a separate approved machine.

## Layout

| Path | Purpose |
| --- | --- |
| `compose.loopback.yaml` | Temporarily exposes only API and R ports on VM loopback for component tests. |
| `k6/static-edge-smoke.js` | One-client public static-edge smoke check. |
| `fixtures/` | Version-controlled, non-secret graph and item fixture inputs. |
| `results/` | Ignored per-run evidence output. |
| `runbook.md` | Operational sequence, safety gates, and abort procedure. |
| `report-template.md` | Required evidence and conclusion structure for each run. |

## Runner convention

All future commands must use the exact k6 image tag above or a documented
native 1.5.x installation. A scenario receives its non-secret configuration
through protected environment input; secrets are never written into this
directory, a command line, k6 output, or a report.

The public endpoint and certificate fingerprint are supplied only after the
preflight stage has approved them. Until then, the smoke script remains a
checked-in template and must not be run with a guessed target.
