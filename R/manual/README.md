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

The service listens on `http://127.0.0.1:8000`. Leave this terminal open.
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

## Run the presentation demo

Open a second terminal at the repository root and run:

```sh
R/manual/demo.sh
```

The demo checks service health, creates a three-node prerequisite model, and
repeatedly submits correct answers until the service returns a final profile.
It prints every JSON response with `jq`.

If the service uses another port:

```sh
KST_BASE_URL=http://127.0.0.1:8080 R/manual/demo.sh
```

The interactive OpenAPI page is available at:

```text
http://127.0.0.1:8000/__docs__/
```

## Send individual requests

Health check:

```sh
curl --silent http://127.0.0.1:8000/health | jq .
```

Create a model:

```sh
curl --silent \
  --request POST \
  --header 'Content-Type: application/json' \
  --data-binary @R/manual/model-request.json \
  http://127.0.0.1:8000/internal/v1/kst/model | jq .
```

An advance request must include the model and posterior returned by the model
request. The demo script shows how to assemble that request with `jq`.

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
