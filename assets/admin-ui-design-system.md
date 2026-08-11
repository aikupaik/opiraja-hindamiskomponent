# Assessment Lab admin UI design system

This document is the implementation brief for the admin UI. It is derived from
`assets/HK_disain.png` (1536 × 1024). The PNG is a visual reference; the rules
below are the source of truth for future UI work so an implementer does not
need to inspect the image.

## Product character

Assessment Lab is a calm, editorial operations console for configuring and
observing assessments. The visual language combines warm paper surfaces,
deep-forest navigation, restrained borders, and serif display headings.

- Prefer clarity, whitespace, and strong information hierarchy over decoration.
- Use forest green for brand, navigation, selected states, and positive status.
- Use semantic accent colors only for meaning: orange/build, amber/warning,
  blue/in-progress, green/success, and red/error.
- Use a white or warm-paper canvas. Avoid gradients, heavy shadows, glassmorphism,
  saturated backgrounds, and decorative illustrations that compete with data.
- The overall tone is precise, quiet, and trustworthy.

## Color palette

These names and hex values are printed in the reference board and must be used
as the shared token vocabulary.

| Token | Hex | Intended use |
| --- | --- | --- |
| `forest-950` | `#0E2D24` | Brand mark, dark sidebar, primary text on dark surfaces |
| `forest-800` | `#16533C` | Primary buttons, active navigation, selected controls |
| `forest-600` | `#2E7D5B` | Links, progress, positive chart series, secondary brand accents |
| `forest-200` | `#CFE6DA` | Soft green fills, selected/positive backgrounds |
| `forest-50` | `#F2F7F4` | Very light green tint behind brand states |
| `paper-50` | `#FAFBF8` | App/page background |
| `paper-100` | `#F1EEE8` | Warm separators, subtle secondary surfaces |
| `surface` | `#FFFFFF` | Cards, panels, inputs, tables |
| `text-primary` | `#1A1F1D` | Main copy and headings |
| `text-muted` | `#66746E` | Supporting copy, metadata, labels |
| `orange-600` | `#E96D2A` | Build category, source-added accent, build status |
| `amber-600` | `#D97706` | Warning status and caution actions |
| `blue-600` | `#2563EB` | Running/in-progress status and series |
| `green-600` | `#16A34A` | Completed/success status |
| `red-600` | `#DC2626` | Failed/error status and destructive feedback |

Use color with a text or icon label for status. Never rely on color alone to
communicate success, failure, or progress.

## Typography

The reference uses three families with deliberately different roles:

| Style | Family | Weight | Size / line height | Use |
| --- | --- | ---: | ---: | --- |
| Display heading | Recoleta | 700 | `48px / 56px` | Page hero headings, used sparingly |
| Section heading | Recoleta | 600 | `32px / 40px` | Primary screen/card headings |
| Heading 3 | Inter | 600 | `20px / 28px` | Card titles and subsections |
| Label | Inter | 500 | `14px / 20px` | Field labels, navigation labels, table headings |
| Body | Inter | 400 | `14px / 20px` | Descriptions and general UI copy |
| Code / data | IBM Plex Mono | 400 | `14px / 20px` | JSON, IDs, technical values, compact metrics |

The reference also uses small metadata and captions. Implement these as Inter
`12px / 16px`, weight 400 or 500, in `text-muted`. Use sentence case for copy;
use uppercase only for small category eyebrows such as `BUILD`, `OBSERVE`, and
`TEST`, with letter spacing around `0.12em`.

Fallback stacks:

```css
font-family: "Recoleta", Georgia, serif;
font-family: Inter, ui-sans-serif, system-ui, sans-serif;
font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace;
```

## Layout and shell

### Shared top bar

- Use a horizontal top bar with a compact circular `OR` mark at the left,
  followed by `ASSESSMENT LAB` and the subtitle `Operator Console`.
- Keep primary areas in the center: `Build`, `Observe`, `Test`, and `Settings`.
  Each area may have a short secondary descriptor, for example `Materials &
  rules`, `System & quality`, `Experiments`, and `Access & system`.
- Show the current operator and a compact `Lock` action on the right.
- The active area uses `forest-800` and a thin underline. Inactive areas use
  `text-primary` or `text-muted` according to emphasis.
- Separate the bar from the page with a light bottom border. Keep it compact;
  it is navigation, not a hero area.

### Page canvas

- Use `paper-50` as the page background and center the content in a spacious
  desktop canvas.
- Use a 2-column dashboard grid for overview pages. The reference uses a wider
  primary column and a secondary column of approximately equal visual weight;
  let CSS grid distribute the available width rather than hard-coding the
  screenshot dimensions.
- Keep page gutters at `20–24px` on desktop, `16px` on narrow screens.
- Use `16–24px` between sibling panels and `24–32px` between major sections.
- On small screens, collapse dashboard columns to one column and allow the
  top navigation to scroll horizontally or collapse behind a menu.

### Optional dark rail

The Experiments screen shows a narrow vertical rail at the left of the content:

- background `forest-950`, white/forest-tinted icons, rounded selected tile;
- one icon per primary destination, with a tooltip or accessible label;
- keep the rail narrow and visually secondary to the content;
- do not put text-only navigation in the rail when the top bar already provides
  the area names.

## Surfaces, borders, and elevation

- Cards and panels use `surface` with a `1px` border in a very light neutral
  derived from `paper-100` (use `#E5E9E6` as the implementation border).
- Use `12px` corner radius for cards and dashboard panels; use `8px` for
  controls and compact status elements; use a full pill for statuses.
- Use minimal elevation: a subtle shadow is acceptable for menus and raised
  interactive cards, but static cards should be legible through border and
  spacing first.
- Panels should have generous internal padding, generally `16–24px`.
- Avoid nested borders where whitespace can define grouping.

## Component rules

### Buttons

- Primary: `forest-800` background, white text, `8px` radius, medium Inter;
  use for the page's main action such as `+ New experiment`.
- Secondary: white surface, neutral border, `text-primary`; use for actions
  such as `View as participant` and `Export report`.
- Tertiary: text-only, usually `forest-800`, with a visible hover background.
- Include a clear icon only when it improves scanning. Keep icon and text
  aligned on a `4–8px` gap.
- Disabled buttons reduce contrast and must not look like active secondary
  actions.

### Inputs and filters

- Inputs and selects use white surface, `1px` neutral border, `8px` radius,
  `14px / 20px` Inter text, and at least `40px` control height.
- Placeholder and supporting text use `text-muted`.
- Filter controls may sit inline in a panel header, as shown by the date range
  and project selector on System & quality.
- Focus must be visible: use a `2px` forest focus ring with sufficient contrast.

### Status chips

Use a pale tint with a semantic border/text pair, plus a text label:

| Status | Accent |
| --- | --- |
| Idle / Draft | neutral: `paper-100` + `text-muted` |
| Running | `blue-600` |
| Completed | `green-600` with `forest-50`/`forest-200` tint |
| Warning | `amber-600` |
| Failed / Error | `red-600` |

Chips are compact, pill-shaped, and never the only indication of state in a
table or timeline.

### Cards

The Materials & rules overview uses three feature cards: `Sources`, `Item bank`,
and `Rules`. Each card contains:

1. a small tinted icon circle;
2. a Recoleta or strong section title;
3. one short explanatory sentence;
4. a bottom metric such as `12 sources` and a right-facing arrow.

Cards should remain clickable as a whole when the destination is the main
action. Keep the metric and arrow aligned at the bottom so cards in a row feel
consistent.

### Tables

- Use a white table surface inside a bordered panel with a compact header row.
- Header labels are small Inter medium text in `text-muted`.
- Body rows use `14px / 20px`; keep row height generous enough to scan.
- Align numbers and times consistently. Use IBM Plex Mono for IDs and technical
  measurements where that improves comparison.
- Use subtle row dividers, not zebra striping by default.
- End table panels with a quiet right-arrow link such as `View all runs`.

### Charts and metrics

- Metric cards show a large value, a concise label, and a comparison line such
  as `vs previous 7 days` plus a semantic delta.
- Charts use a restrained grid and the palette accents. Green is completed,
  blue is running, and red is failed in the timeline legend.
- Avoid 3D effects and unnecessary chart decoration. Always include a text
  legend and accessible summary for charts.
- The Run detail page uses a progress timeline, a performance line chart, an
  issues panel, and recent feedback. Each chart belongs in its own bordered
  panel with a clear title.

### Alerts

Use a bordered, lightly tinted horizontal alert with an information icon and
plain-language message. The reference shows an informational alert in blue;
semantic warning/error alerts should follow the same geometry with amber/red
tokens.

### Icons and illustrations

- Use simple line icons with consistent stroke weight, rounded joins, and a
  16–20px visual box.
- Use icon circles for feature cards and activity rows; tint the circle instead
  of filling the icon heavily.
- The Materials & rules hero illustration is a sparse connected set of document,
  code, and rule tiles. It is supportive, not required to understand the page.
- Prefer the existing icon system in the application. If no icon exists, add a
  small inline SVG with an accessible label rather than introducing a new icon
  library solely for decoration.

## Screen composition references

### Materials & rules

- Eyebrow: `BUILD` in orange.
- Page title: `Materials & rules`.
- Supporting text explains that the page creates knowledge context and
  authoring rules for the assessment agent.
- Three feature cards: Sources, Item bank, Rules.
- A `Recent activity` table occupies the lower section and ends with `View all
  activity`.

### System & quality

- Eyebrow: `OBSERVE`.
- Page title: `System & quality`.
- Header filters: date range and project selector.
- Four metric cards: Runs, Success rate, Avg. duration, Errors.
- Middle row: Run timeline chart and Top issues list.
- Lower section: Recent runs table with status chips.

### Experiments

- Eyebrow: `TEST`.
- Page title: `Experiments` and a primary `+ New experiment` action.
- Four summary metrics: Active experiments, Participants, Completed, In
  progress.
- Main table includes Experiment, Goal, Status, Participants, Progress, and
  Updated.
- Keep progress bars compact and pair them with a percentage label.

### Run #128

- Breadcrumbs above the title: `Experiments / Trial run – v5 / Run #128`.
- Title row includes a Completed chip and actions for participant view, export,
  and an overflow menu.
- Tab bar: Overview, Participants, Timeline, Feedback, Diagnostics.
- Overview uses three panels: Run progress, Performance, and Issues; a Recent
  feedback panel sits below the larger content area.

## Accessibility and interaction

- Meet WCAG AA contrast for body text and controls. The muted color is for
  secondary copy, not small critical text on white.
- Every icon-only action needs an accessible name and a visible tooltip on hover
  where the meaning is not obvious.
- Preserve keyboard focus order across header, filters, cards, tables, and
  actions. Do not make a whole card keyboard-inaccessible when it is clickable.
- Use hover, focus, selected, disabled, loading, empty, and error states for
  interactive components. Keep layout stable while data loads.
- Respect reduced-motion preferences; status changes and chart transitions must
  not be required to understand the interface.

## Token usage

Use `admin-ui.tokens.css` when writing CSS and `admin-ui.tokens.json` when a
component system, test, or design-token pipeline needs structured values. Do
not add one-off colors or arbitrary font sizes without first checking these
files.

