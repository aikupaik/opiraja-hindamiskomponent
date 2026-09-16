import katex from 'katex'
import 'katex/contrib/mhchem'
import './math-content.css'

export type MathTextProps = {
  text: string
}

export type TruncatedMathText = {
  text: string
  truncated: boolean
}

type TextSegment = {
  kind: 'text'
  source: string
}

type MathSegment = {
  kind: 'math'
  expression: string
  source: string
}

type MathTextSegment = TextSegment | MathSegment

type OpeningDelimiter = {
  escaped: boolean
  index: number
  token: string
}

const INLINE_OPEN = '\\('
const INLINE_CLOSE = '\\)'
const ESCAPED_INLINE_OPEN = '\\\\('
const ESCAPED_INLINE_CLOSE = '\\\\)'
const ELLIPSIS = '…'

export function MathText({ text }: MathTextProps) {
  return parseMathText(text).map((segment, index) => {
    if (segment.kind === 'text') return segment.source

    try {
      const html = katex.renderToString(segment.expression, {
        displayMode: false,
        globalGroup: false,
        maxExpand: 1000,
        output: 'mathml',
        strict: 'warn',
        throwOnError: true,
        trust: false,
      })
      return (
        <span
          className="math-content-formula"
          // KaTeX generates this HTML from an isolated expression with trust disabled.
          dangerouslySetInnerHTML={{ __html: html }}
          key={index}
        />
      )
    } catch {
      return segment.source
    }
  })
}

export function truncateMathText(
  text: string,
  maximumLength: number,
): TruncatedMathText {
  if (!Number.isInteger(maximumLength) || maximumLength < 0) {
    throw new RangeError('maximumLength must be a non-negative integer')
  }

  if (Array.from(text).length <= maximumLength) {
    return { text, truncated: false }
  }

  const segments = parseMathText(text)
  let preview = ''
  let usedCharacters = 0

  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index]
    const characters = Array.from(segment.source)
    const remaining = maximumLength - usedCharacters

    if (characters.length <= remaining) {
      preview += segment.source
      usedCharacters += characters.length
      continue
    }

    if (segment.kind === 'text') {
      preview += characters.slice(0, Math.max(remaining, 0)).join('')
      return { text: `${preview.trimEnd()}${ELLIPSIS}`, truncated: true }
    }

    if (preview.length === 0) {
      preview = segment.source
      const hasFollowingContent = segments
        .slice(index + 1)
        .some((following) => following.source.length > 0)
      return hasFollowingContent
        ? { text: `${preview}${ELLIPSIS}`, truncated: true }
        : { text: preview, truncated: false }
    }

    return { text: `${preview.trimEnd()}${ELLIPSIS}`, truncated: true }
  }

  return { text: preview, truncated: false }
}

function parseMathText(text: string): MathTextSegment[] {
  const segments: MathTextSegment[] = []
  let plainTextStart = 0
  let searchStart = 0

  while (searchStart < text.length) {
    const opening = findOpeningDelimiter(text, searchStart)
    if (opening === null) break

    const closingToken = opening.escaped
      ? ESCAPED_INLINE_CLOSE
      : INLINE_CLOSE
    const expressionStart = opening.index + opening.token.length
    const closingIndex = text.indexOf(closingToken, expressionStart)
    const nestedOpening = findOpeningDelimiter(text, expressionStart)

    if (
      closingIndex === -1 ||
      (nestedOpening !== null && nestedOpening.index < closingIndex)
    ) {
      searchStart = nestedOpening?.index ?? expressionStart
      continue
    }

    if (opening.index > plainTextStart) {
      segments.push({
        kind: 'text',
        source: text.slice(plainTextStart, opening.index),
      })
    }

    const sourceEnd = closingIndex + closingToken.length
    const rawExpression = text.slice(expressionStart, closingIndex)
    segments.push({
      kind: 'math',
      expression: opening.escaped
        ? removeOneEscapeLayer(rawExpression)
        : rawExpression,
      source: text.slice(opening.index, sourceEnd),
    })
    plainTextStart = sourceEnd
    searchStart = sourceEnd
  }

  if (plainTextStart < text.length) {
    segments.push({ kind: 'text', source: text.slice(plainTextStart) })
  }

  return segments.length > 0 ? segments : [{ kind: 'text', source: text }]
}

function findOpeningDelimiter(
  text: string,
  searchStart: number,
): OpeningDelimiter | null {
  const escapedIndex = text.indexOf(ESCAPED_INLINE_OPEN, searchStart)
  const standardIndex = text.indexOf(INLINE_OPEN, searchStart)

  if (
    escapedIndex !== -1 &&
    (standardIndex === -1 || escapedIndex < standardIndex)
  ) {
    return { escaped: true, index: escapedIndex, token: ESCAPED_INLINE_OPEN }
  }
  if (standardIndex !== -1) {
    return { escaped: false, index: standardIndex, token: INLINE_OPEN }
  }
  return null
}

function removeOneEscapeLayer(value: string): string {
  return value.replaceAll('\\\\', '\\')
}
