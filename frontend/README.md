# Õpiraja test player

This directory is the learner-facing React/Vite application. It is deliberately
separate from the operator dashboard in `admin/`: the applications have
different users, state lifecycles, presentation, and runtime containers.

Learner links carry a test-bound JWT only in `#token=`. The app moves it into a
test-specific `sessionStorage` entry, removes the fragment before API work, and
attaches it through the centralized client. An authenticated `401` clears that
test's token. Query parameters and persistent local storage are never used for
credentials.

## Local development

Run FastAPI on `127.0.0.1:8000`, then start the player:

```console
npm install
npm run dev
```

Open a real assessment at
`http://127.0.0.1:5173/test/{canonical-test-uuid}`. Vite proxies `/api` to the
local FastAPI process. Development uses a `/` asset base; production builds use
`/test/` and emit hashed assets under `/test/assets/`.

Quality gates:

```console
npm test
npm run lint
npm run build
```

## Runtime and recovery behavior

Every valid page load calls the idempotent player `start` endpoint and rebuilds
the screen from persisted backend state. The browser stores no question,
answer, or credential state. A preparing assessment polls only after a `202`,
using `Retry-After` plus positive jitter. Active and completed reloads return
the same persisted question or feedback.

An uncertain answer failure keeps the exact submitted `submission_id` and
`option_id` for an explicit retry. A `409` instead reloads authoritative state
through `start`. The UI never shows correctness, answer keys, item IDs,
submission IDs, posterior data, or internal graph identity.

## Authorization boundary

The player link carries a signed, test-bound JWT in its fragment. The
credential source in `src/credential.ts` is the single bootstrap and storage
boundary. It isolates credentials by path test ID, ignores query credentials,
and clears the active test credential after an authenticated `401`.

## Production routing

The `player` container serves only `/test/*`, `/test/assets/*`, and its internal
`/nginx-health` endpoint. It has no host port and never proxies API traffic.
The public `web` container owns `127.0.0.1:8080`, forwards `/test/*` to this
container, and continues to forward browser `/api/*` calls to FastAPI on the
same origin. Bare `/test` remains `404`.
