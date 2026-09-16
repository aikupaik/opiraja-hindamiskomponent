# LaTeX and Chemistry Rendering Plan

## Summary

- Use **KaTeX** with its official `mhchem` extension. It is fast, supports
  accessible MathML, works cleanly with React/Vite, and does not require
  runtime DOM scanning.
- Render formulas only in the public test player and the admin simulation.
  Leave admin item CRUD fields raw.
- Recognize inline `\(...\)` formulas and their extra-escaped
  `\\(...\\)` equivalent. Do not interpret `$...$` or display-math
  delimiters.

## Implementation changes

- Add a shared `@opiraja/math-content` package used by both applications,
  with:
  - `MathText({ text })` for rendering mixed prose and formulas.
  - `truncateMathText(text, maximumLength)` returning math-safe preview text
    plus a `truncated` flag.
  - KaTeX CSS and the `mhchem` extension for expressions such as
    `\(\ce{H2O}\)`.
- Parse text into plain-text and formula segments:
  - Preserve ordinary text and backslashes unchanged.
  - For `\\(...\\)` segments, remove exactly one escaping layer from the
    delimiters and formula contents.
  - Support multiple formulas within one string.
  - Leave unmatched delimiters as ordinary text.
  - If KaTeX rejects a formula, show its original source instead of breaking
    the page.
- Render with accessible native MathML, `trust: false`, bounded macro
  expansion, and no user-defined persistent macros. MathML-only output avoids
  KaTeX's inline HTML styles and font assets so it remains compatible with the
  deployment's strict CSP. Plain content remains React text rather than
  injected HTML.
- Apply rendering to:
  - `frontend/` active-question instruction, stimulus, prompt, and all answer
    options.
  - `frontend/` completed-test question/stimulus previews, student answers,
    and correct answers.
  - `admin/` simulation instruction, stimulus, prompt, and answer options.
- Preserve completed-result truncation without cutting through a formula
  delimiter or expression.
- Add shared styling so inline formulas inherit surrounding font sizing and
  alignment. Wide formulas receive localized horizontal overflow rather than
  expanding the page.
- Tighten admin option CSS selectors so the answer-letter badge styles do not
  affect KaTeX's nested spans.
- Add the shared package dependency and lockfile entries to both applications,
  and copy the new package in both Docker build stages before `npm ci`.

## Public interfaces

- New shared component: `MathTextProps { text: string }`.
- New helper result: `{ text: string; truncated: boolean }`.
- No API, database, or backend schema changes; normalization is display-only
  and never mutates stored formula text.

## Test plan

- Unit-test ordinary text, standard delimiters, double-escaped delimiters,
  multiple mixed formulas, fractions, `mhchem` chemistry, unmatched
  delimiters, invalid LaTeX fallback, and preservation of unrelated
  backslashes.
- Verify untrusted HTML-like text remains text and KaTeX trust-requiring
  commands cannot create active links or HTML.
- Verify preview truncation never cuts through a recognized formula.
- Add player integration coverage for formulas in prompts, choices, completed
  student answers, and correct answers.
- Add admin simulation coverage for formulas in its question and choice
  rendering, while confirming item CRUD remains raw.
- Run `npm run lint`, `npm test`, and `npm run build` in both `frontend/` and
  `admin/`, then build both Docker images to verify the shared local dependency
  is packaged correctly.

## Assumptions

- Chemistry-specific expressions use KaTeX/mhchem syntax such as `\ce{...}`
  inside `\(...\)`.
- Only inline parenthesis delimiters are supported in this feature; bracket
  and dollar delimiters remain literal text.
- Feedback summaries, graph-node labels, reports, diagnostics, and admin item
  review/editing are outside this rendering scope.
