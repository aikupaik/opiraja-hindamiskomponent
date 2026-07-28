# Manual KST service demo

This harness runs the production KST router locally and adds console logging.
It does not change the production router, configuration, or automated tests.

## First-time environment setup

The project requires R 4.6.1 and uses `renv` for package versions. From the
repository root:

```sh
cd R
Rscript -e 'renv::restore(prompt = FALSE); renv::status()'
cd ..
```

## Start the service

From the repository root:

```sh
Rscript R/manual/run_service.R
```

The service listens on `http://127.0.0.1:8001`. Leave this terminal open.
Every request produces a method, path, response status, and duration log.
Press Ctrl+C to stop the service.

To include formatted request and response bodies in the service console:

```sh
KST_LOG_BODIES=true Rscript R/manual/run_service.R
```

The host and port can also be changed:

```sh
KST_HOST=127.0.0.1 KST_PORT=8080 Rscript R/manual/run_service.R
```

Keep the host as `127.0.0.1` for a local-only demonstration. Binding to
`0.0.0.0` makes the service reachable through other network interfaces.

## Run the v2 experiment

Open a second terminal at the repository root and run:

```sh
R/manual/demo_v2.sh
```

The experiment checks service health, creates a three-node prerequisite
model, selects from the supplied candidate inventory, and submits correct
answers without reusing candidates. The small example inventory deliberately
demonstrates explicit `item_inventory_exhausted` completion. Every JSON
response is printed with `jq`.

The original v1 characterization demo remains available as
`R/manual/demo.sh`.

If the service uses another port:

```sh
KST_BASE_URL=http://127.0.0.1:8080 R/manual/demo_v2.sh
```

The interactive OpenAPI page is available at:

```text
http://127.0.0.1:8001/__docs__/
```

## Send individual requests

Health check:

```sh
curl --silent http://127.0.0.1:8001/health | jq .
```

Create a model:

```sh
curl --silent \
  --request POST \
  --header 'Content-Type: application/json' \
  --data-binary @R/manual/model-v2-request.json \
  http://127.0.0.1:8001/internal/v2/kst/model | jq .
```

For v2, pass the returned model and posterior to `/internal/v2/kst/select`
with `R/manual/candidates-v2.json`. Advancement also includes the concrete
administered descriptor and the ordered remaining candidates. The existing
`demo.sh` remains the frozen v1 characterization demo.

## Try alternate KST parameters

The harness includes a separate valid configuration so that the committed
prototype baseline remains unchanged:

```sh
KST_CONFIG_PATH=R/manual/experimental-kst.json \
  Rscript R/manual/run_service.R
```

Run the same demo in the second terminal and compare when it stops and how it
builds the final profile.

Configuration files must be canonical JSON: recursively sorted keys, no
formatting whitespace, and no trailing newline. The production loader rejects
non-canonical files. The experimental file meets these requirements.
