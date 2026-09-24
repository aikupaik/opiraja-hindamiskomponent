# Assessment Lab TalTech UI design system

This document is the implementation brief for the admin UI. It is derived from
`assets/HK_disain.png` (1536 × 1024) and aligned with TalTech’s official brand
guidelines. The PNG remains a visual reference; this document and the token
files are the source of truth for future UI work.

The TalTech reference is the [official brand materials](https://taltech.ee/en/brand)
and its [brand guideline PDF](https://haldus.taltech.ee/sites/default/files/2023-10/TalTech%20CVI_A4_2022_lingitud_small.pdf).

## Product character

Assessment Lab is a clear, focused assessment experience for configuring,
delivering, and observing tests. The visual language uses TalTech burgundy and
magenta as brand signals, light blue and dark blue as supporting accents, white
surfaces, restrained borders, and geometric sans-serif typography.

- Prefer clarity, whitespace, and strong information hierarchy over decoration.
- Use TalTech burgundy for primary actions and brand emphasis, and magenta only
  as a deliberate accent.
- Use TalTech dark blue and light blue for supporting emphasis, links, focus,
  and information states.
- Use white and cool-neutral surfaces. Avoid gradients, heavy shadows, glassmorphism,
  saturated backgrounds, and decorative illustrations that compete with data.
- The overall tone is precise, quiet, and trustworthy.

## Color palette

These names and hex values are the shared token vocabulary for TalTech-aligned
Assessment Lab UI work.

| Token | Hex | Intended use |
| --- | --- | --- |
| `burgundy` | `#AA1352` | Primary actions, brand mark, selected controls |
| `magenta` | `#E4067E` | Brand accent and emphasis; use sparingly |
| `light-blue` | `#4DBED2` | Focus rings, information accents, positive visual highlights |
| `dark-blue` | `#342B60` | Supporting emphasis, links, running/in-progress states |
| `grey-1` | `#9396B0` | Secondary muted UI and metadata |
| `grey-2` | `#DADAE4` | Borders, dividers, neutral status surfaces |
| `page` | `#F7F7FA` | App/page background |
| `surface` | `#FFFFFF` | Cards, panels, inputs, tables |
| `text-primary` | `#17151A` | Main copy and headings |
| `text-muted` | `#555565` | Supporting copy, metadata, labels |
| `success` | `#2F6F44` | Completed/success status |
| `warning` | `#8A5A00` | Warning status and caution actions |
| `error` | `#9B1C31` | Failed/error status and destructive feedback |
| `border` | `#DADAE4` | Card and panel borders |
| `focus-ring` | `#4DBED2` | Keyboard focus indicator |

Use color with a text or icon label for status. Never rely on color alone to
communicate success, failure, or progress.

## Typography

TalTech’s brand typeface is Proxima Nova. Use the following stacks so the UI
remains usable when the licensed font is unavailable:

| Style | Family | Weight | Size / line height | Use |
| --- | --- | ---: | ---: | --- |
| Display heading | Proxima Nova | 700 | `48px / 47px` | Page hero headings, uppercase |
| Section heading | Proxima Nova | 700 | `32px / 29px` | Primary screen/card headings, uppercase |
| Heading 3 | Proxima Nova | 700 | `20px / 20px` | Card titles and subsections, uppercase |
| Label | Proxima Nova | 500 | `14px / 20px` | Field labels, navigation labels, table headings |
| Body | Proxima Nova | 400 | `16px / 24px` | Descriptions and general UI copy |
| Code / data | IBM Plex Mono | 400 | `14px / 20px` | JSON, IDs, technical values, compact metrics |

Use Proxima Nova `12px / 16px`, weight 400 or 500, in `text-muted` for metadata
and captions. Keep body copy in sentence case. Headlines and sub-headings use
uppercase with tight leading, following TalTech guidance.

Fallback stacks:

```css
font-family: "Proxima Nova", Verdana, sans-serif;
font-family: "IBM Plex Mono", Consolas, monospace;
```

## Layout and shell

### Shared top bar

- Use a horizontal top bar with a compact circular `OR` mark at the left,
  followed by `ASSESSMENT LAB` and the subtitle `Operator Console`.
- Keep primary areas in the center: `Build`, `Observe`, `Test`, and `Settings`.
  Each area may have a short secondary descriptor, for example `Materials &
  rules`, `System & quality`, `Experiments`, and `Access & system`.
- Show the current operator and a compact `Lock` action on the right.
- The active area uses `burgundy` and a thin underline. Inactive areas use
  `text-primary` or `text-muted` according to emphasis.
- Separate the bar from the page with a light bottom border. Keep it compact;
  it is navigation, not a hero area.

### Page canvas

- Use `page` as the page background and center the content in a spacious
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

- background `dark-blue`, white/light-blue icons, rounded selected tile;
- one icon per primary destination, with a tooltip or accessible label;
- keep the rail narrow and visually secondary to the content;
- do not put text-only navigation in the rail when the top bar already provides
  the area names.

## Surfaces, borders, and elevation

- Cards and panels use `surface` with a `1px` `border` (`#DADAE4`).
- Use `12px` corner radius for cards and dashboard panels; use `8px` for
  controls and compact status elements; use a full pill for statuses.
- Use minimal elevation: a subtle shadow is acceptable for menus and raised
  interactive cards, but static cards should be legible through border and
  spacing first.
- Panels should have generous internal padding, generally `16–24px`.
- Avoid nested borders where whitespace can define grouping.

## Component rules

### Buttons

- Primary: `burgundy` background, white text, `8px` radius, medium Proxima Nova;
  use for the page's main action such as `+ New experiment`.
- Secondary: white surface, neutral border, `text-primary`; use for actions
  such as `View as participant` and `Export report`.
- Tertiary: text-only, usually `burgundy`, with a visible hover background.
- Include a clear icon only when it improves scanning. Keep icon and text
  aligned on a `4–8px` gap.
- Disabled buttons reduce contrast and must not look like active secondary
  actions.

### Inputs and filters

- Inputs and selects use white surface, `1px` neutral border, `8px` radius,
  `14px / 20px` Proxima Nova text, and at least `40px` control height.
- Placeholder and supporting text use `text-muted`.
- Filter controls may sit inline in a panel header, as shown by the date range
  and project selector on System & quality.
- Focus must be visible: use a `2px` light-blue focus ring with sufficient contrast.

### Status chips

Use a pale tint with a semantic border/text pair, plus a text label:

| Status | Accent |
| --- | --- |
| Idle / Draft | neutral: `grey-2` + `text-muted` |
| Running | `dark-blue` with a cool-neutral tint |
| Completed | semantic `success` with a pale green tint |
| Warning | semantic `warning` |
| Failed / Error | semantic `error` |

Chips are compact, pill-shaped, and never the only indication of state in a
table or timeline.

### Cards

The Materials & rules overview uses three feature cards: `Sources`, `Item bank`,
and `Rules`. Each card contains:

1. a small tinted icon circle;
2. a strong Proxima Nova section title;
3. one short explanatory sentence;
4. a bottom metric such as `12 sources` and a right-facing arrow.

Cards should remain clickable as a whole when the destination is the main
action. Keep the metric and arrow aligned at the bottom so cards in a row feel
consistent.

### Tables

- Use a white table surface inside a bordered panel with a compact header row.
- Header labels are small Proxima Nova medium text in `text-muted`.
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

- Eyebrow: `BUILD` in burgundy or magenta.
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
