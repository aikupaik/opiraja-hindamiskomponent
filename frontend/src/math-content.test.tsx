import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MathText, truncateMathText } from '@opiraja/math-content'

describe('MathText', () => {
  it('renders standard and double-escaped inline formulas in mixed text', () => {
    const { container } = render(
      <p>
        <MathText
          text={String.raw`First \(\frac{15}{21}\), then \\(\\frac{5}{6}\\).`}
        />
      </p>,
    )

    const formulas = container.querySelectorAll('.math-content-formula')
    expect(formulas).toHaveLength(2)
    expect(formulas[0].querySelector('annotation')).toHaveTextContent(
      String.raw`\frac{15}{21}`,
    )
    expect(formulas[1].querySelector('annotation')).toHaveTextContent(
      String.raw`\frac{5}{6}`,
    )
    expect(container.querySelectorAll('math')).toHaveLength(2)
    expect(container).toHaveTextContent('First')
    expect(container).toHaveTextContent('then')
  })

  it('renders mhchem expressions', () => {
    const { container } = render(
      <MathText text={String.raw`Water forms as \(\ce{2H2 + O2 -> 2H2O}\).`} />,
    )

    expect(container.querySelector('.math-content-formula')).not.toBeNull()
    expect(container.querySelector('annotation')).toHaveTextContent(
      String.raw`\ce{2H2 + O2 -> 2H2O}`,
    )
  })

  it('preserves unmatched, invalid, and unrelated escaped text', () => {
    const value = String.raw`C:\temp stays raw; \(unfinished; \(\unknown{1}\)`
    const { container } = render(<MathText text={value} />)

    expect(container).toHaveTextContent(value)
    expect(container.querySelector('.math-content-formula')).toBeNull()
  })

  it('does not turn untrusted text or KaTeX links into active HTML', () => {
    const { container } = render(
      <MathText
        text={String.raw`<img src=x onerror=alert(1)> \(\href{javascript:alert(1)}{bad}\)`}
      />,
    )

    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('a')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror=alert(1)>')
  })
})

describe('truncateMathText', () => {
  it('truncates Unicode text by characters', () => {
    expect(truncateMathText('Õun 🍎 laual', 4)).toEqual({
      text: 'Õun…',
      truncated: true,
    })
  })

  it('never cuts through a formula', () => {
    const value = String.raw`12345 \(\frac{15}{21}\) trailing text`
    const result = truncateMathText(value, 12)

    expect(result).toEqual({ text: '12345…', truncated: true })
    expect(result.text).not.toContain(String.raw`\(`)
  })

  it('keeps a formula that is the entire value even when its source is long', () => {
    const value = String.raw`\(\frac{123456789}{987654321}\)`

    expect(truncateMathText(value, 5)).toEqual({
      text: value,
      truncated: false,
    })
  })
})
