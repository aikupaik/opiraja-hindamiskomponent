# Assessment Lab — TalTech digital design contract

Status: design baseline for later implementation in `admin/` and `frontend/`.
This document does not change either application.

The goal is not to make Assessment Lab look like a marketing campaign. The
goal is to make both applications feel like parts of the same TalTech digital
environment: recognisable, restrained, accessible, and consistent.

## Authority and scope

Use the sources in this order when rules conflict:

1. [TalTech Digital Environments design system (DKS)](https://www.figma.com/proto/G4eaZg8SwP2BDLp2BiC6yq/Design--Styleguide?node-id=6653-15393&page-id=3241%3A69246&scaling=min-zoom&starting-point-node-id=6653%3A15393&type=design)
   for digital foundations and component appearance.
2. [TalTech brand materials](https://taltech.ee/en/brand) and the
   [TalTech brand guideline PDF](https://haldus.taltech.ee/sites/default/files/2023-10/TalTech%20CVI_A4_2022_lingitud_small.pdf)
   for the logo, core palette, typography, and brand usage.
3. [TalTech accessibility statement](https://taltech.ee/en/accessibility),
   WCAG 2.2 AA, and EN 301 549 for interaction and accessibility requirements.
4. This document for Assessment Lab-specific decisions where TalTech guidance
   does not define a product behaviour.

The DKS describes itself as a common visual base rather than an exhaustive set
of fixed rules. This document selects and formalises the parts Assessment Lab
will use. Rules labelled **Assessment Lab decision** are local adaptations, not
claims about the TalTech brand.

`assets/HK_disain.png` remains useful for product content and information
architecture, but its forest palette, serif headings, rounded-card language,
and `OR` mark are not TalTech design-system rules. It is not a visual source of
truth.

`assets/admin-ui.tokens.css` and `assets/admin-ui.tokens.json` implement the
foundation defined by this contract. Components use the semantic token names;
legacy palette and typography aliases have been removed.

## Design principles

- **TalTech first.** Use the DKS dark purple as the primary digital colour,
  magenta as the secondary interactive colour, Proxima Nova typography, a
  light neutral canvas, and generous white space.
- **One shared language.** Admin and learner experiences use the same tokens,
  controls, interaction states, and accessibility behaviours. Density and
  composition may differ, but components must not drift visually.
- **Task over decoration.** Hierarchy comes from typography, spacing, and
  elevation. Avoid ornamental gradients, oversized radii, glass effects, and
  decorative imagery that competes with assessment content.
- **Explicit states.** Every asynchronous or editable surface accounts for
  loading, empty, success, warning, error, disabled, hover, active, and focus
  states where relevant.
- **Accessible by default.** Colour supports meaning but never carries it
  alone. Semantic HTML, keyboard operation, clear labels, and visible focus are
  component requirements, not later enhancements.

## Colour

### Core digital palette

The DKS defines colour ranges from 100 to 900 but recommends supporting only
the values the product actually needs. Use semantic aliases in components;
raw palette values belong only in the token layer.

| Palette token | Hex | Assessment Lab role |
| --- | --- | --- |
| `purple-500` | `#342B60` | Primary action, selected navigation, strong heading accent |
| `purple-600` | `#272048` | Primary hover/active and dark brand surface |
| `pink-100` | `#FEEBF5` | Subtle secondary tint |
| `pink-500` | `#E4067E` | Secondary action, link, selected form control |
| `pink-600` | `#AB055F` | Secondary hover/active |
| `cyan-100` | `#EDF9FB` | Subtle accent surface |
| `cyan-500` | `#4DBED2` | Focus outline and supporting accent; not body text on white |
| `burgundy-500` | `#AA1352` | Secondary brand accent, not the default digital CTA |
| `green-500` | `#62BB46` | TalTech sustainability accent only; do not use as generic success |

The CVI also defines black and white. DKS neutrals are more useful for product
interfaces:

| Neutral token | Hex | Use |
| --- | --- | --- |
| `gray-100` | `#FBFBFC` | Page canvas |
| `gray-200` | `#F6F6F8` | Recessed/background surface |
| `gray-300` | `#EDEDF2` | Dividers and subtle borders |
| `gray-400` | `#DADAE4` | Light component background and stronger border |
| `gray-500` | `#C9CBD8` | Disabled border or background |
| `gray-600` | `#9396B0` | Subtle icons and non-critical metadata |
| `gray-700` | `#6E7184` | Disabled text |
| `gray-800` | `#4A4B58` | Labels and secondary text |
| `gray-900` | `#25262C` | Default text |
| `white` | `#FFFFFF` | Main surface; use generously |

### Semantic colour roles

Use the DKS notification palette, not ad-hoc product colours.

| Role | Base | Dark | Light surface | Required use |
| --- | --- | --- | --- | --- |
| Info | `blue-500` `#2468B0` | `blue-600` `#1B4E84` | `blue-100` `#E9F0F7` | Neutral system information |
| Success | `teal-500` `#41BD90` | `teal-600` `#277257` | `teal-100` `#ECF8F4` | Completed or successful operation |
| Warning | `yellow-500` `#FFC75A` | `yellow-700` `#80642D` | `yellow-100` `#FFF9EF` | Caution or recoverable risk |
| Danger | `red-500` `#E95D77` | `red-700` `#752E3B` | `red-100` `#FDEFF1` | Error, failure, or destructive action |

Use dark variants for text, icons, rails, and filled controls when the base
colour does not provide sufficient contrast. For example, cyan, teal, yellow,
and red base colours are accents on light surfaces, not automatic white-text
backgrounds. Verify every foreground/background pair at its rendered size.

### Semantic aliases

Both applications must consume the same aliases rather than interpreting the
palette independently:

```text
canvas             gray-100
surface            white
surface-subtle     gray-200
border-subtle      gray-300
border             gray-400
text               gray-900
text-secondary     gray-800
text-subtle        gray-600
text-disabled      gray-700
action-primary     purple-500
action-primary-*   purple-600
action-secondary   pink-500
action-secondary-* pink-600
focus              cyan-500
```

Do not introduce a raw hex value in component CSS. Add a reviewed semantic
token first. Gradients are reserved for approved TalTech logo artwork and
brand communication; application controls use solid colours.

## Typography

TalTech's brand typeface is Proxima Nova. DKS uses a `16px` (`1rem`) base and
Verdana when Proxima Nova is unavailable.

```css
font-family: "Proxima Nova", Verdana, sans-serif;
```

Use licensed, self-hosted font files if they are made available to the project.
Do not fetch Proxima Nova from an unapproved public CDN. The fallback must be
tested rather than treated as an exceptional state.

### UI type scale

| Style | Size / line height | Weight | Use |
| --- | --- | --- | --- |
| H1 | `28px / 36px` | Black (`900`) | Page title |
| H2 | `26px / 32px` | ExtraBold (`800`) | Major section |
| H3 | `24px / 28px` | Bold (`700`) | Panel group |
| H4 | `20px / 24px` | ExtraBold (`800`) | Card or subsection title |
| H5 | `18px / 24px` | Bold (`700`) | Compact heading |
| H6 | `16px / 20px` | Black (`900`) | Small strong heading |
| Lead | `18px / 24px` | Regular or Bold | Introductory copy or key value |
| Body | `16px / 24px` | Regular or Bold | Default copy and control text |
| Small | `14px / 20px` | Regular or Bold | Dense admin content and table text |
| Label | `12px / 16px` | Regular or Bold | Labels and metadata only |
| Table | `14px / 20px` | Regular; Bold header | Default data table |

Do not restore the prototype's 48px display heading or introduce serif display
faces. Do not use 12px for essential instructions or interactive text.

The CVI uses uppercase Proxima Nova for brand headlines and sub-headings.
Within Assessment Lab:

- use uppercase only for short page/section display headings and compact
  eyebrows where it remains easy to scan;
- use sentence case for navigation, buttons, form labels, table headings,
  statuses, learner instructions, questions, and body copy;
- never uppercase user-authored content or long multi-line text;
- keep heading letter spacing tight and avoid custom negative tracking that
  harms screen readability.

**Assessment Lab decision:** a system monospace stack may be used for source
code, JSON, hashes, and opaque identifiers. It is not a TalTech brand font and
must not be used for ordinary metrics, dates, or tables.

## Spacing, grid, and responsive layout

DKS uses an 8px square baseline grid across mobile, tablet, and desktop. Use
`4px` only for micro-spacing within a component. The normal scale is:

| Token | Value | Typical use |
| --- | ---: | --- |
| `space-0` | `0` | Intentional reset |
| `space-1` | `4px` | Icon/text micro-gap |
| `space-2` | `8px` | Compact internal gap |
| `space-3` | `16px` | Default component/content gap |
| `space-4` | `24px` | Section or card padding |
| `space-5` | `32px` | Major group separation |
| `space-6` | `48px` | Page-section separation |

`12px` is allowed by DKS only as a rare component padding exception. New
layouts should prefer the 8px sequence. Larger spaces continue in 8px steps.

Use a responsive 12-column grid. Hierarchy is `container → row → column →
content`; do not position page content against the viewport independently of
the container.

| Viewport | DKS breakpoint | Page side padding | Grid/content gap |
| --- | --- | ---: | ---: |
| `360–576px` | X-Small | `8px` | `16px` |
| `577–767px` | Small | `16px` | `16px` |
| `768–991px` | Medium | `16px` | `16px` |
| `992–1199px` | Large | `32px` | `24px` |
| `1200–1399px` | Extra Large | `32px` | `24px` |
| `1400–1919px` | XX Large | `32px` | `24px` |
| `1920px+` | XXX Large | `32px` | `24px` |

The application shell may grow to `1920px`; reading columns, forms, and learner
questions must use narrower measure. Admin dashboards can use more columns but
must collapse without horizontal page scrolling. Data tables may scroll inside
their own labelled container.

## Shape and elevation

TalTech DKS controls are compact and restrained.

- Buttons, icon buttons, and tags use a full pill shape.
- Text fields, selects, alerts, cards, menus, and panels use a small `4px`
  radius. Do not use the prototype's `8–12px` general-purpose radii.
- Use borders and spacing before shadows to separate content.
- Elevation `0` is the canvas/recessed background.
- Elevation `1` is the default light shadow for cards that need separation.
- Elevation `2` is for elements that must sit above ordinary cards, such as a
  sticky application header.
- Elevation `3` is for floating layers such as dialogs and popovers.
- Never use elevation alone to express selected, invalid, or disabled state.

## Shared component contract

### Buttons and links

- Medium is the default button size; small is for dense secondary admin
  actions. The minimum target box is `40px` high; icon-only controls keep an
  equivalent square target.
- Use at most one primary button per section. Primary is solid `purple-500`
  with white text; hover/active uses `purple-600`.
- Secondary is solid `pink-500`; use it for a genuine second call to action,
  not every adjacent action.
- Light is a neutral low-emphasis button. Tertiary is text plus an optional
  directional icon. Outlined primary is the normal alternative to a filled
  primary.
- Danger styles are only for destructive or difficult-to-reverse actions.
  Success styles are only for an action that completes a journey, such as
  Submit, Confirm, or Save; they are not a generic positive decoration.
- Icons may appear before or after text. Icon-only buttons require an
  accessible name and a tooltip when their meaning is not universal.
- Implement default, hover, focus, active, disabled, and loading states without
  changing the button's dimensions. Loading blocks duplicate activation.
- A link navigates and a button performs an action. Style does not change the
  correct HTML element.

### Form controls

- Every control has a persistent visible label above it. Placeholder text is
  an example or format hint, never the label.
- Inputs, textareas, selects, radios, checkboxes, and toggles use the same label,
  hint, required, disabled, and validation language in both applications.
- Default control text is `16px / 24px`; dense admin-only controls may use
  `14px / 20px` while preserving the `40px` target height.
- Use a white container, neutral border, `4px` radius, and enough contrast from
  the surrounding surface. Hover darkens the border; focus adds a visible cyan
  outline without removing the border.
- Place helper, error, warning, success, or info text directly below the
  control. Pair it with an icon and text; do not signal validation by border
  colour alone.
- Checkbox groups allow multiple independent choices. Radio groups choose one
  of a set. Use a toggle only for a setting that takes effect immediately.
- Required and optional state must be explicit and consistent across a form.

### Cards and panels

- A card contains content and actions about one subject and must be easy to
  scan. Do not use a card merely to put a border around arbitrary layout.
- Default background is white. Available tinted surfaces are secondary-light,
  accent-light, neutral-light, and gray-200; reserve them for a meaningful
  distinction, not alternating decoration.
- Use `16px` or `24px` padding by default. DKS also permits `8px`, rare `12px`,
  and `40px` for specific compositions.
- Keep title, optional subtext, body, and actions in that order. Align repeated
  cards to a common grid.
- Use elevation 1 only when the card needs separation from its container.
  Otherwise a subtle border or background difference is enough.
- A dismissible card has a labelled close action; do not make a card
  dismissible solely to reduce visual density.

### Alerts and inline feedback

- Alerts communicate a short, important state change without interrupting the
  task. Place page-level alerts at the top of the primary content area and use
  them sparingly.
- Structure: semantic colour rail, matching icon, short title, concise body,
  optional action link, and optional close control.
- Supported tones are success, danger/error, warning, info, and neutral/light.
- Dismissible alerts are keyboard operable. Focus the action before the close
  control in DOM order; `Escape` may dismiss only when that behaviour is
  announced and does not discard important work.
- Use `role="alert"` for urgent errors and `role="status"` or a polite live
  region for non-urgent updates. Avoid announcing the same message twice.

### Tags and statuses

- Tags categorise or filter content. Status tags report application state.
- Keep labels to one or two words. Avoid excessive tag use and never encode a
  status with colour alone.
- DKS supports regular and filled variants, each with an optional leading
  icon, in primary, secondary, success, warning, danger, info, light, and dark
  tones.
- Use the regular/light variant in dense tables. Filled variants are for
  stronger, infrequent emphasis.
- Tags scale with their immediate text context but must retain readable type
  and adequate padding.
- Assessment states map to semantics: Draft/Idle → neutral; Preparing/Running →
  info; Completed → success; Needs attention → warning; Failed → danger.

### Tables and data display

- Use `14px / 20px` regular for cells and Bold for column headings. Keep all
  headers explicit, including visually hidden headers where appropriate.
- Align text left. Align comparable numeric values consistently and use
  tabular numerals when the licensed font supports them.
- Prefer subtle row dividers and whitespace to zebra striping. Reserve tinted
  rows for a real semantic state.
- Provide sorting state in text/ARIA as well as an icon. Do not put essential
  actions behind hover-only affordances.
- On narrow screens, either recompose simple data into labelled records or
  keep a complex table in a horizontally scrollable, focusable region with an
  accessible name.
- Charts use the semantic palette and include a legend, values available to
  assistive technology, and a short text summary. Never distinguish series by
  colour alone.

### Navigation, dialogs, and overlays

- The admin shell may use persistent application navigation; the learner shell
  should show only the identity, progress, language/help actions, and actions
  needed for the current assessment step.
- Mark the current route with text semantics (`aria-current`) in addition to
  the purple/magenta visual treatment.
- Menus, dropdowns, tooltips, and popovers use elevation 3 only while floating.
  Restore focus to the trigger when they close.
- Dialogs trap focus, have a labelled title, support `Escape` where safe, and
  require an explicit action for destructive confirmation.
- Provide a skip link before repeated application navigation.

## Brand and icon use

- Use only official TalTech logo artwork supplied for web. Never redraw,
  recolour, outline, distort, add effects to, or alter the spacing of the logo.
- Keep the Assessment Lab name separate from the logo's protected area. An
  internal product mark may identify Assessment Lab but must not imitate or
  replace the institutional logo.
- Use the approved white/negative logo only on a sufficiently contrasting dark
  surface. The monochrome black logo is a fallback when colour is technically
  impossible, not a default web treatment.
- Do not duplicate the word `TalTech` next to a logo when the artwork already
  contains it.
- Use a single, consistent line-icon family with rounded joins and an optical
  size around `20px`. Decorative icons are hidden from assistive technology;
  meaningful icons receive a text alternative through their control.

## Product-specific composition

### Admin application

- Optimise for repeated operational work: clear page title, a restrained
  action area, filters adjacent to the data they affect, and dense but readable
  tables.
- Use dashboard metrics only when they support a decision. A large value needs
  a label, time range or comparison context, and semantic change text.
- Keep one primary action per page section. Bulk and destructive actions remain
  visually separated from the normal path.
- Preserve the content model shown in `HK_disain.png` only where it still
  matches implemented routes; do not reproduce its visual styling.

### Learner application

- Keep the assessment surface calm and linear. Show one question and one
  dominant next action at a time.
- Render answer choices as a labelled radio group with a large clickable area.
  Selection must remain visible in high contrast and at 200% zoom.
- Progress must be truthful and understandable without colour. Do not imply an
  exact question count when the adaptive flow cannot know it.
- Do not use admin density, diagnostic status colours, charts, or technical
  identifiers in the learner journey.
- Completion and feedback use the same typography, spacing, alerts, and
  semantic colours as admin, with wider measure and more vertical space.

## Accessibility and interaction baseline

- Meet WCAG 2.2 AA and the applicable EN 301 549 requirements.
- Keep visible focus on every interactive element. Use a `2px` cyan focus
  outline with offset and add a darker adjacent edge where cyan alone would not
  contrast with the background.
- Preserve logical heading order, landmark regions, label/control association,
  keyboard order, and screen-reader names.
- Target at least `40 × 40px` controls; never go below the WCAG 2.2 minimum
  target requirements or rely on tightly packed icon targets.
- Text and controls reflow at 320 CSS px and 400% zoom without loss of content
  or two-dimensional page scrolling, except intrinsically two-dimensional data
  such as complex tables.
- Respect `prefers-reduced-motion`. Motion must not be required to notice a
  state change or understand progress.
- Maintain layout during loading. Prefer a labelled progress indicator or
  content-shaped skeleton; never use colour animation as the only signal.
- Error text identifies the problem and the recovery action in plain language.
  Move focus only when needed to recover, and never erase valid user input.
- Test both Estonian and English copy. Components must accommodate longer text
  without truncating essential labels.

## Implementation acceptance criteria

The CSS/JSON foundations are aligned with this document. UI implementation
must now:

1. Create one shared semantic token set consumed by both `admin/` and
   `frontend/`; do not maintain two independent palettes or type scales.
2. Implement shared primitives for button/link, field controls, alert, tag,
   card/panel, table container, focus treatment, and loading state before
   restyling feature pages.
3. Remove legacy forest/orange and serif-display aliases instead of silently
   remapping misleading names to TalTech colours.
4. Add visual examples for every variant and state, including the Verdana
   fallback, narrow viewport, 200% zoom, long Estonian copy, and reduced motion.
5. Check automated contrast and keyboard behaviour, then manually verify focus,
   reflow, screen-reader names, and status announcements.
6. Compare representative admin and learner screens side by side. They should
   share foundations and controls while retaining the appropriate information
   density for each audience.

Any deliberate exception must be documented next to the affected token or
component with its accessibility impact and product rationale.
