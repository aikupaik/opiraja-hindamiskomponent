import { describe, expect, it } from 'vitest'
import { parseTestPath } from './path'

describe('parseTestPath', () => {
  it('accepts a canonical hyphenated UUID case-insensitively', () => {
    expect(
      parseTestPath('/test/ABCD1234-5678-4ABC-8DEF-1234567890AB'),
    ).toBe('abcd1234-5678-4abc-8def-1234567890ab')
    expect(parseTestPath('/test/00000000-0000-0000-0000-000000000000')).toBe(
      '00000000-0000-0000-0000-000000000000',
    )
  })

  it.each([
    '/test',
    '/test/',
    '/test/not-a-uuid',
    '/test/abcd123456784abc8def1234567890ab',
    '/test/abcd1234-5678-4abc-8def-1234567890ab/extra',
    '/other/abcd1234-5678-4abc-8def-1234567890ab',
  ])('rejects invalid path %s', (path) => {
    expect(parseTestPath(path)).toBeNull()
  })
})
