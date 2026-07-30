import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildReportHtml,
  downloadReportHtml,
  downloadReportJson,
  reportFilename,
} from './report'
import { exampleReport } from './test/reportFixture'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('simulation report downloads', () => {
  it('builds standalone script-free HTML with escaped report values', () => {
    const html = buildReportHtml(exampleReport)

    expect(html).toContain('<!doctype html>')
    expect(html).toContain('<meta charset="utf-8">')
    expect(html).not.toContain('<script>')
    expect(html).toContain(
      'A &lt;script&gt;alert(&quot;unsafe&quot;)&lt;/script&gt;',
    )
    expect(html).toContain('Incomplete &lt;diagnostic&gt;')
    expect(html).not.toContain('Authorization')
  })

  it('uses stable UTC filenames and the requested MIME types', () => {
    const createObjectURL = vi.fn((_blob: Blob) => 'blob:report')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    downloadReportHtml(exampleReport)
    downloadReportJson(exampleReport)

    expect(reportFilename(exampleReport, 'html')).toBe(
      'simulation-report-10000000-0000-4000-8000-000000000001-20260729T091011Z.html',
    )
    const htmlBlob = createObjectURL.mock.calls[0]?.[0]
    const jsonBlob = createObjectURL.mock.calls[1]?.[0]
    expect(htmlBlob).toBeInstanceOf(Blob)
    expect(jsonBlob).toBeInstanceOf(Blob)
    expect((htmlBlob as Blob).type).toBe('text/html;charset=utf-8')
    expect((jsonBlob as Blob).type).toBe('application/json;charset=utf-8')
    expect(revokeObjectURL).toHaveBeenCalledTimes(2)
  })
})
