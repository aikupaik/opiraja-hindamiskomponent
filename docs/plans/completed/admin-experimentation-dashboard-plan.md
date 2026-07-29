# Admin and experimentation dashboard

## Summary

Build the blank React/Vite `admin` project into a three-page dashboard backed
exclusively by FastAPI. The dashboard provides:

1. course source-material and YG-rule management;
2. full item-bank auditing and controlled item revision;
3. manual end-to-end assessment simulation with scoped diagnostics.

Admin database access lives in a separate `backend/app/admin/` package with
its own repository protocol and `SupabaseAdminRepository`. The existing
`AssessmentRepository` remains focused on OR/player behavior. Reuse the same
lifespan-managed Supabase client rather than creating another connection
pool.

No database migration is required. Experiment diagnostics are ephemeral,
scoped to one experiment, and never added to normal production logs.

## Backend and API changes

### Admin authorization foundation

- Add a replaceable admin authorization seam using
  `Authorization: Bearer <ADMIN_ACCESS_KEY>`.
- Keep the expected key only in the backend `.env`, compare it in constant
  time, and never bundle it into Vite or write it to logs. Add the example to `.env.example`.
- Missing or invalid credentials return `401`. If `ADMIN_ACCESS_KEY` is not
  configured, admin endpoints are disabled.
- Extend `AuthContext` with an admin actor and explicit read, write,
  diagnostics, and simulation scopes so real JWT authorization can later
  replace the development key without changing route handlers.
- Allow a valid admin actor to use the existing test-creation and player
  routes for simulations. Preserve the current phase-one permissive behavior
  for ordinary OR/player requests.

### Admin repository and interfaces

Keep admin DTOs, persistence mappings, repository code, ingestion, routes,
and diagnostics in `backend/app/admin/`. Do not add admin CRUD methods to
`AssessmentRepository`.

Add these authenticated admin interfaces:

| Method | Endpoint | Behavior |
|---|---|---|
| `GET` | `/api/v1/admin/session` | Validate the key and return admin capabilities and graph limits. |
| `GET` | `/api/v1/admin/courses` | Derive course choices from `repo_materjalid`. |
| `GET` | `/api/v1/admin/source-materials?course=…` | Return material metadata and content previews for a course. |
| `GET` | `/api/v1/admin/source-materials/{id}` | Return the complete extracted material text. |
| `POST` | `/api/v1/admin/source-materials` | Add a source through multipart course fields, an optional URL, and an optional PDF/TXT/Markdown upload. |
| `GET` | `/api/v1/admin/yg-rules?course=…` | Return rules for the selected course. |
| `POST` | `/api/v1/admin/yg-rules` | Insert a course, rule description, and valid JSON example. |
| `GET` | `/api/v1/admin/items?course=…&limit=…&offset=…` | Return a paginated, exact-course audit view of `ylesandepank`. |
| `PUT` | `/api/v1/admin/items/{yp_id}` | Update the existing item or create a revised copy, according to the request mode. |
| `GET` | `/api/v1/admin/experiments/{experiment_id}/events` | Stream the authenticated in-memory diagnostic buffer for one experiment. |

Use the existing stable API error envelope. Return `404` for missing rows,
`413` for configured ingestion limits, `422` for invalid item/source content,
`502` or `504` for remote source failures, and `503` for unavailable
persistence.

### Course and source-material behavior

- Derive course choices only from `repo_materjalid`.
- Use `kursus` as the course value and `pealkiri` as its human title. In the selection, include both: "pealkiri (kursus)". For a
  defensive legacy row whose course code is null, use `pealkiri` as both
  label and value.
- When multiple material rows use the same course code, use the newest
  nonblank title for the course-selector label.
- Treat `repo_materjalid.pealkiri` as the course title and allow it to repeat
  across multiple source rows.
- Require a nonblank course code/title and at least one of source URL or
  uploaded file.
- When both URL and file are supplied, extract the uploaded file but retain
  the URL as provenance. With a file only, store its original filename in
  `allika_url`.
- Accept PDF, UTF-8 text, and Markdown uploads. URL responses may additionally
  be HTML.
- Use `pypdf` for PDF extraction, Beautiful Soup for readable HTML text, and
  `python-multipart` for uploads. Run blocking parsing in a worker thread.
- Do not store source binaries and do not implement OCR. Reject encrypted,
  unsupported, oversized, or textless/scanned PDFs without inserting a row.
- Fetch public HTTP(S) URLs only. Reject credentials, localhost,
  private/link-local/non-global addresses, and redirects to those targets.
  Revalidate every redirect and enforce configurable byte, page,
  extracted-text, redirect, and timeout limits.
- Store and display YG rules, but do not change YG behavior in this phase.
  `naidis_json` must be valid non-null JSON and defaults to `{}` in the form.

### Item-bank audit and revision

The item read model contains all fields required for inspection, including
course and graph metadata, content, status, measurement parameters, usage
telemetry, and timestamps.

The item editor may change only:

- `juhis`
- `tyvi`
- `stiimul`
- `voti`
- `distraktor_1`
- `distraktor_2`
- `distraktor_3`
- `staatus`
- `irt_a`
- `irt_b`
- `beeta_error`
- `g_guess`

Expose every `ItemStatus` choice using English API values and the existing
database mapping:

| API value | Database value |
|---|---|
| `draft` | `kavand` |
| `usable` | `kasutatav` |
| `review` | `läbi vaatamisel` |
| `archived` | `arhiivis` |

The update request contains a complete editable-field snapshot plus one of
these modes:

1. `update_existing`
   - Update the selected `yp_id` in place.
   - Preserve `kursus`, `graafi_objekt`, `graafi_ema_objekt`,
     `kognitiivne_tase`, `skoor`, `kasutamiste_arv`,
     `viimane_kasutus`, and every other non-editable field.
   - Preserve the existing usage telemetry.
   - Return the updated row.
   - Require explicit UI confirmation because content, status, or parameter
     changes can affect active sessions that reference this item.

2. `create_copy`
   - Load the source row, overlay the submitted editable fields, and insert a
     new row without supplying `yp_id`, allowing the database to generate it.
   - Preserve course, graph node/parent, cognitive level, score, and all other
     non-editable metadata from the source.
   - Set `kasutamiste_arv = 0` and `viimane_kasutus = NULL`.
   - Leave the source item unchanged, including its status.
   - Return the newly created row and its new `yp_id`.

Default the UI to `create_copy`, because it preserves the historical meaning
of item IDs and avoids silently changing snapshotted assessment inventory.
Do not automatically archive the source item when a copy is created.

Validate the complete resulting row before either write:

- reject non-finite measurement values;
- require `beeta_error` and `g_guess` to be within `[0, 1]`;
- require schema-required content fields;
- when the resulting status is `usable`, require a domain-valid usable
  question with sufficient distinct answer choices;
- reject fields outside the editable allowlist.

Both write modes must update at most one source target and return the
canonical row read back from Supabase. If an in-place update archives or
otherwise invalidates an item referenced by an active assessment, keep the
existing inventory-exhaustion behavior as the runtime fallback.

## React admin UI

Replace the Vite starter in `admin/src/` with a typed application using plain
React state, CSS, and hash-based navigation. Do not add a global state or
component library.

- Add an unlock screen that validates the operator-entered key against
  `/api/v1/admin/session`, stores it only in `sessionStorage`, sends it as a
  bearer token, and supports explicit locking.
- Add a shared typed API client, consistent loading/error/empty states,
  abortable requests, and cleanup for polling and event streams.
- Configure the Vite development server to proxy `/api` to FastAPI so admin
  requests remain same-origin and do not require broad CORS.

### Source materials

- Show course selection and course creation fields.
- Keep material ingestion and YG-rule creation as separate forms on the same
  page.
- The material form contains course code, course title, URL, and file picker.
  Show the selected source, extraction errors, and the saved content preview.
- Refresh material and rule lists after insertion. Allow expanding a material
  to read its complete extracted text.
- Validate rule example JSON before submission.

### Item-bank audit

- Provide an editable course-code combobox and explicit Search action.
- Show a paginated table with ID, node, cognitive level, question stem,
  status, use count, and last use.
- Expand a row to inspect instruction, stimulus, key, distractors, parent
  node, score, and IRT/BLIM parameters.
- Open editing in a focused form prefilled with the complete editable field
  set.
- Present `Create revised copy` and `Update current item` as mutually
  exclusive save modes, defaulting to copy.
- Explain which metadata and telemetry will be preserved or reset before
  submission.
- Require a confirmation dialog for in-place updates, with a stronger warning
  when status or measurement parameters change.
- After success, refresh the source row and, for copy mode, display and
  highlight the new `yp_id`.

### Test simulation

- Form fields:
  - `user_id`
  - `learning_path_id`
  - course selected from source-material-derived choices
  - goal labeled `Real test` or `Trial run`, stored as `real_test` or
    `trial_run`
  - dynamic nodes
  - relation rows whose endpoints select from the entered nodes
- Keep method fixed to `kst` and cognitive level at the existing default
  `mõistab`.
- Use the existing OR/player endpoints directly:
  - create with `POST /api/v1/tests`;
  - poll `POST /api/v1/player/tests/{test_id}/start`, respecting
    `Retry-After`;
  - render and submit each question manually;
  - continue until final feedback is displayed.
- Provide cancel/reset controls, prevent duplicate submission, and keep the
  simulated player visually light.
- Use a desktop split layout with the test and terminal side-by-side, stacking
  them on narrow screens.

## Experiment diagnostics

- Generate an `experiment_id` before creation, open its event stream, and send
  that ID with the valid admin bearer credential on every test/player request.
- Capture only authenticated, correlated activity:
  - exact assessment creation, start, and answer request bodies;
  - client response bodies, statuses, and request IDs;
  - FastAPI structured completion fields and warnings;
  - exact FastAPI-to-R request and R-to-FastAPI response JSON, including
    models, selections, posterior values, and correctness;
  - Supabase operation names, counts, and timings, but not raw headers or
    service credentials.
- Keep standard logs unchanged: they continue to exclude bodies,
  authorization headers, keys, and secrets.
- Emit sequenced events with timestamp, source, level, type, request/test IDs,
  and payload. Use FastAPI SSE over authenticated `fetch` streaming so the
  browser can provide the bearer header.
- Maintain a 500-event ring buffer per experiment, expire it after 60 minutes
  of inactivity, support replay after the last sequence, and clean up
  disconnected subscribers.
- Document that diagnostics are process-local, do not survive restarts, and
  are intended for the current single-process experimentation environment.

## Tests and acceptance

### Backend

- Admin-key validation, scopes, missing configuration, and redaction.
- Course aggregation, duplicate-code title selection, and null-code fallback.
- Material/rule row mappings and Supabase failure handling.
- Uploaded PDF/TXT/Markdown, HTML/text/PDF URLs, upload-over-URL precedence,
  safe redirects, private-address rejection, size/page limits,
  encrypted/textless PDFs, unsupported content, and no insert after failure.
- Exact-course item search, pagination, and complete item decoding.
- Every ItemStatus mapping in both write modes.
- In-place updates change only editable fields and preserve source metadata,
  ID, usage count, and last-use timestamp.
- Copy updates preserve non-editable metadata, apply edited values, generate a
  new ID, reset usage count/last use, and leave the source row unchanged.
- Invalid numeric/content combinations, extra fields, missing items, and
  multi-row write anomalies are rejected.
- Diagnostic correlation, test and R bodies, ordering/replay, expiry/bounds,
  disconnect cleanup, uncorrelated-request exclusion, and secret redaction.
- Existing OR/player creation, start, answer, and retry behavior remains
  covered and unchanged.

### React

- Unlocking, invalid keys, session storage, locking, and protected-page
  behavior.
- Course selection and material/rule form validation.
- Audit search, pagination, expanded item details, full field editing, status
  choices, save-mode default, warnings, confirmation, and returned copy ID.
- Preparation polling with `Retry-After`, cancellation, manual answering,
  double-submit prevention, and final feedback.
- Diagnostic stream rendering, replay/reconnect, cleanup, and redaction.

Run from the backend virtual environment:

```sh
cd backend
source .venv/bin/activate
python -m pytest
python -m pyright
```

Run from the admin project:

```sh
cd admin
npm test
npm run lint
npm run build
```

Update `.env.example` and the backend/admin READMEs with
`ADMIN_ACCESS_KEY`, ingestion/diagnostic limits, local startup, the Vite API
proxy, and the single-process diagnostics limitation.

## Assumptions and exclusions

- No course table, persistent experiment-log table, binary file storage, OCR,
  YG rule execution, or automatic source-item archival is added.
- The defensive null-course fallback is implemented even though the currently
  deployed schema marks `repo_materjalid.kursus` non-null and its currently
  visible rows contain course codes.
- In-place item editing is intentionally supported despite its risk to active
  session inventory; the UI warns the administrator and copy mode remains the
  default.
- Existing uncommitted assessment-service changes are preserved.
- `ATA_kst/` and `TP_kst/` remain read-only reference code.
