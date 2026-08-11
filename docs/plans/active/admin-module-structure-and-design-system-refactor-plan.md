# Admin Module Structure and Design-System Refactor Plan

## Summary

Refactor the admin application in reviewable stages: first introduce a
feature-oriented project structure and behavior-preserving extractions, then
add reusable UI components, and finally migrate every existing screen to the
design system in `assets/`.

Backend APIs and workflow behavior will not change. 

The navigation will use four Estonian product areas:

- **Koosta** — Materials and questions;
- **Jälgi** — an honest empty System and Quality future view;
- **Testi** — Simulation and test player;
- **Seaded** — KST parameters.

Existing hash URLs will remain valid, and `#/observe` will be added for the
future System and Quality area.

## 1. Project Structure and Responsibility Boundaries

Adopt the following structure:

```text
src/
  app/
    App.tsx
    AppShell.tsx
    routeConfig.ts
    useHashRoute.ts
  features/
    auth/
    materials/
    items/
    experiments/
      shared/
      simulation/
      player-demo/
    kst-configuration/
    system-quality/
  shared/
    api/
    layout/
    ui/
    styles/
    lib/
  test/
```

- Keep `App.tsx` responsible only for application composition, the
  authentication gate, and selecting the active route.
- Define typed areas, child destinations, English internal identifiers,
  Estonian display labels and descriptions, and hash-route mappings in
  `routeConfig.ts`.
- Move the generic HTTP client, error normalization, and shared course loading
  into `shared/api/`. Keep domain DTOs and endpoint functions with their
  corresponding features.
- Split the current broad `App.test.tsx` into shell, authentication, and
  feature tests colocated with the functionality they cover.
- Remove `App.css` and the current `index.css` after migration. Only design
  tokens, reset rules, base typography, and global accessibility rules should
  remain global.

The route and navigation mapping will be:

| Area | Description | Destinations |
| --- | --- | --- |
| `Koosta` | `Materjalid ja reeglid` | `#/materials`, `#/items` |
| `Jälgi` | `Süsteem ja kvaliteet` | `#/observe` |
| `Testi` | `Katsed` | `#/simulation`, `#/player-demo` |
| `Seaded` | `Ligipääs ja süsteem` | `#/kst-parameters` |

`#/materials` remains the default route. The active area is derived from the
current feature route, and areas with multiple destinations display a
secondary feature navigation.

## 2. Reusable Components and Feature Decomposition

Create shared components only where the application has real repeated
behavior or styling:

- `Button` and `ButtonLink` with primary, secondary, tertiary, and icon
  variants;
- `Panel`, `PageHeader`, `Alert`, `StatusChip`, `EmptyState`,
  `TableContainer`, and `FormField`;
- an accessible `Dialog` built on the native `<dialog>` element;
- `TopBar`, `AreaNavigation`, `FeatureNavigation`, and `PageContainer`;
- small line-style inline SVG icon components, without adding an icon library.

Split feature responsibilities as follows:

- **Authentication:** isolate credential storage, session restoration, login,
  lock, and the unlock screen. Session expiry must continue to clear the JWT
  and return the operator to the unlock screen.
- **Materials:** separate the data-loading hook, material upload form, YG rule
  form, material list, and rule list. Keep course refresh behavior after a
  newly introduced course is saved.
- **Items:** separate search and pagination state, the item table, expandable
  details, and the editor dialog. Move validation and item-to-editable DTO
  conversion into pure functions.
- **Experiment shared functionality:** keep the test-definition form and its
  validation under `experiments/shared/` because both simulation and player
  demo use it.
- **Simulation:** extract an experiment lifecycle hook, player preview,
  diagnostics panel, report panel, and report-download logic. The hook owns
  request cancellation, polling, SSE lifecycle, answer submission, and report
  loading.
- **Player demo:** extract its create-and-monitor lifecycle hook, player-link
  panel, and completion feedback. The hook owns sequential polling, timers,
  request cancellation, pause, retry, and reset behavior.
- **KST configuration:** extract the configuration hook, draft form, pure
  calculated-limit function, preview table, and version history.
- **System and Quality:** add a reusable empty-state screen for `#/observe`.
  It must not display fabricated metrics or make new API calls.

Do not introduce a global state library. Keep feature state in feature hooks,
pass shared course choices from the application boundary, and use React
context only if prop passing through the new shell would otherwise become
multi-level plumbing.

## 3. Design-System Migration

- Import `assets/admin-ui.tokens.css` as the canonical token source before the
  application global styles. Update the admin Docker build to copy that token
  file into the build context so local and container builds use the same
  source of truth.
- Use colocated CSS Modules for shared components and feature layouts. Remove
  the current alternative color variables, inline style objects, one-off
  colors, and arbitrary font sizes.
- Use the Recoleta, Inter, and IBM Plex Mono fallback stacks defined by the
  tokens. No external font request or new font dependency will be introduced
  because the repository does not include licensed font files.
- Build a compact white top bar containing the OR mark,
  `Hindamislabor / Operaatori vaade`, the four area links, the current
  operator, and the `Lukusta` action. Use the forest active state and thin
  underline from the design rules.
- On narrow screens, keep the top and secondary navigation horizontally
  scrollable rather than adding a new menu interaction.
- Use `paper-50` for the page canvas, centered desktop content, 20–24 px
  desktop gutters, 16 px narrow-screen gutters, token spacing, 12 px panel
  radii, 8 px control radii, and single-column mobile layouts.
- Preserve each workflow's content while migrating materials, items,
  simulation, player demo, KST configuration, the Observe placeholder, and the
  unlock screen to the shared page headers, panels, forms, tables, alerts, and
  status components.
- Render every status with an Estonian text label and, where useful, an icon.
  Color must never be the only state indicator.
- Use IBM Plex Mono for IDs, hashes, JSON, diagnostic payloads, and technical
  measurements where it improves comparison.
- Implement item editing as a real modal dialog with Escape handling, focus
  containment, focus restoration, an accessible title, and
  `aria-modal="true"` behavior supplied by native modal dialog semantics.
- Provide visible focus states, disabled/loading/empty/error/success states,
  `aria-live` announcements, accessible icon-button names, horizontally
  scrollable table wrappers, and `prefers-reduced-motion` handling.
- Do not add the optional dark experiment rail in this refactor. The top bar
  and secondary navigation provide the required hierarchy and leave room for
  the rail to be introduced with a future experiments overview.

## 4. Delivery Stages

### Stage 1: Structure and behavior-preserving extraction

- Create the app, feature, and shared folder boundaries.
- Move API contracts and endpoint calls to their owning features.
- Extract feature hooks and pure domain functions without changing visible
  behavior or CSS.
- Split and relocate tests while preserving the existing 20-test baseline.

### Stage 2: UI foundation and application shell

- Connect the canonical design tokens and CSS Module structure.
- Implement the shared UI and layout components.
- Replace the flat five-link header with the four-area shell and feature
  navigation.
- Add the `#/observe` placeholder and preserve every existing route.

### Stage 3: Feature migration

Migrate screens in this order so shared patterns stabilize before the most
stateful workflows:

1. Materials and rules;
2. Item bank and editor dialog;
3. Simulation and player demo;
4. KST configuration;
5. Unlock screen.

Remove migrated global selectors after each feature rather than maintaining
two styling systems until the end.

### Stage 4: Cleanup and accessibility review

- Remove the old global stylesheet and dead imports after the last feature is
  migrated.
- Confirm keyboard, focus, responsive, reduced-motion, and semantic-state
  behavior across the whole admin application.
- Confirm that developer-facing names and code remain English while visible
  product copy remains Estonian.

## 5. Internal Interfaces and Compatibility

No backend API, request payload, response DTO, authentication scope, or stored
data contract will change.

Add the following internal frontend interfaces:

- `AdminAreaId` and `AdminRouteId` unions plus route metadata used by the shell;
- a semantic status tone such as `neutral`, `running`, `success`, `warning`,
  or `error` for `StatusChip` and `Alert`;
- typed feature API functions that hide URL construction from components;
- explicit hook result types exposing feature state and permitted actions;
- stable shared component props for visual variants, loading state, accessible
  labels, and optional leading icons.

Preserve the current hash routes and externally visible behavior. Renaming and
moving frontend modules is internal and does not require compatibility export
files once all application imports and tests migrate together.

## 6. Test and Acceptance Plan

Maintain or add automated coverage for:

- login exchange, session restoration, locking, authenticated `401` expiry,
  and never persisting the raw access key;
- every existing hash route, the active area and secondary link, the default
  route, and the new `#/observe` empty state;
- material and rule loading/saving, rule JSON validation, and course refresh;
- item search, pagination, expanded details, safe-copy default mode,
  validation, confirmation behavior, save, and dialog keyboard behavior;
- test-definition validation and prerequisite relations;
- simulation creation, SSE filtering, retry timing, cancellation, answer
  submission, terminal cleanup, report loading, retry, and downloads;
- player-demo creation, sequential polling, pause/retry/reset, cleanup on
  unmount, copy feedback, completion, and failure;
- KST draft editing, calculated limits, save, activation, and history states;
- shared alert/status semantics, dialog focus restoration, icon-button names,
  and loading, empty, error, disabled, and success states.

After every stage, run:

```sh
cd admin
npm test
npm run lint
npm run build
```

After the token import and Dockerfile change, also build the admin container
from the repository root. Before completion, manually verify the application
at approximately 320 px, 760 px, 1100 px, and desktop widths, including
keyboard-only navigation.

## Assumptions

- Backend behavior, security boundaries, API payloads, and workflow semantics
  are out of scope for this refactor.
- No router, global state, UI, styling, chart, font, or icon library will be
  added.
- `Jälgi` is an Estonian placeholder for a future System and Quality feature,
  not a mock dashboard.
- Existing bookmarks continue to work, and `#/materials` remains the default.
- All user-facing UI text is Estonian. Plans, code, identifiers, comments, and
  developer-facing documentation are English.
