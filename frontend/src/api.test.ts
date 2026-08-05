import { describe, expect, it, vi } from 'vitest'
import { createPlayerApi, PlayerApiError } from './api'

const testId = 'abcd1234-5678-4abc-8def-1234567890ab'
const submissionId = '11111111-1111-4111-8111-111111111111'

function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

const active = {
  status: 'active',
  question: {
    submission_id: submissionId,
    item_id: 42,
    instruction: 'Vali üks vastus.',
    prompt: 'Mis on kaks pluss kaks?',
    stimulus: null,
    options: [
      { id: 'opaque-b', text: 'Kolm' },
      { id: 'opaque-a', text: 'Neli' },
    ],
  },
}

describe('player API client', () => {
  it('sends exact start and answer requests without permissive credentials', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(active))
      .mockResolvedValueOnce(jsonResponse(active))
    const api = createPlayerApi({ fetcher })

    await api.start(testId, new AbortController().signal)
    await api.submit(
      testId,
      { submission_id: submissionId, option_id: 'opaque-a' },
      new AbortController().signal,
    )

    const [startUrl, startInit] = fetcher.mock.calls[0]
    expect(startUrl).toBe(`/api/v1/player/tests/${testId}/start`)
    expect(startInit.method).toBe('POST')
    expect(startInit.body).toBeUndefined()
    expect(startInit.headers.get('Authorization')).toBeNull()

    const [answerUrl, answerInit] = fetcher.mock.calls[1]
    expect(answerUrl).toBe(`/api/v1/player/tests/${testId}/answers`)
    expect(answerInit.method).toBe('POST')
    expect(answerInit.body).toBe(
      JSON.stringify({ submission_id: submissionId, option_id: 'opaque-a' }),
    )
    expect(answerInit.headers.get('Content-Type')).toBe('application/json')
  })

  it('conditionally attaches the credential supplied at request time', async () => {
    let credential: string | null = 'short-lived-token'
    const fetcher = vi.fn().mockImplementation(() => jsonResponse(active))
    const api = createPlayerApi({
      fetcher,
      credentialSource: { getCredential: () => credential },
    })

    await api.start(testId, new AbortController().signal)
    credential = null
    await api.start(testId, new AbortController().signal)

    expect(fetcher.mock.calls[0][1].headers.get('Authorization')).toBe(
      'Bearer short-lived-token',
    )
    expect(fetcher.mock.calls[1][1].headers.get('Authorization')).toBeNull()
  })

  it('decodes preparing delay and completed feedback', async () => {
    const completed = {
      status: 'completed',
      feedback: {
        already_mastered: ['Liitmine'],
        learn_next: [],
        review: ['Murrud'],
        summary: null,
        confidence_limited: true,
      },
    }
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ status: 'preparing' }, 202, { 'Retry-After': '7' }),
      )
      .mockResolvedValueOnce(jsonResponse(completed))
    const api = createPlayerApi({ fetcher })

    await expect(api.start(testId, new AbortController().signal)).resolves.toEqual(
      { status: 'preparing', retryAfterSeconds: 7 },
    )
    await expect(api.start(testId, new AbortController().signal)).resolves.toEqual(
      completed,
    )
  })

  it.each([null, '', '3.5', '-2', 'tomorrow'])(
    'falls back to three seconds for Retry-After %s',
    async (retryAfter) => {
      const headers: Record<string, string> =
        retryAfter === null ? {} : { 'Retry-After': retryAfter }
      const api = createPlayerApi({
        fetcher: vi.fn().mockResolvedValue(
          jsonResponse({ status: 'preparing' }, 202, headers),
        ),
      })
      await expect(
        api.start(testId, new AbortController().signal),
      ).resolves.toMatchObject({ retryAfterSeconds: 3 })
    },
  )

  it.each([
    [403, 'forbidden'],
    [404, 'not_found'],
    [409, 'conflict'],
    [503, 'unavailable'],
  ] as const)('maps HTTP %s to %s and retains request ID', async (status, kind) => {
    const api = createPlayerApi({
      fetcher: vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'documented_code', message: 'Backend detail' } },
          status,
          { 'X-Request-ID': 'request-123' },
        ),
      ),
    })

    const error = await api
      .start(testId, new AbortController().signal)
      .catch((reason: unknown) => reason)
    expect(error).toBeInstanceOf(PlayerApiError)
    if (!(error instanceof PlayerApiError)) throw new Error('expected API error')
    expect(error).toMatchObject({
      kind,
      requestId: 'request-123',
      code: 'documented_code',
    })
    expect(error.message).not.toContain('Backend detail')
  })

  it('recognizes FastAPI validation errors and rejects malformed success data', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: [{ loc: ['body'], msg: 'Invalid', type: 'value_error' }] },
          422,
        ),
      )
      .mockResolvedValueOnce(
        new Response('<html>bad gateway</html>', {
          status: 200,
          headers: { 'X-Request-ID': 'malformed-1' },
        }),
      )
    const api = createPlayerApi({ fetcher })

    await expect(
      api.start(testId, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'validation' })
    await expect(
      api.start(testId, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'malformed', requestId: 'malformed-1' })
  })

  it('keeps definitive HTTP meaning when an error body is not JSON', async () => {
    const api = createPlayerApi({
      fetcher: vi.fn().mockResolvedValue(
        new Response('<html>forbidden</html>', {
          status: 403,
          headers: { 'X-Request-ID': 'edge-request' },
        }),
      ),
    })

    await expect(
      api.start(testId, new AbortController().signal),
    ).rejects.toMatchObject({
      kind: 'forbidden',
      status: 403,
      requestId: 'edge-request',
    })
  })

  it('maps transport and abort failures separately', async () => {
    const api = createPlayerApi({
      fetcher: vi.fn().mockRejectedValue(new TypeError('offline')),
    })
    await expect(
      api.start(testId, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'network' })

    const controller = new AbortController()
    controller.abort()
    await expect(api.start(testId, controller.signal)).rejects.toMatchObject({
      kind: 'aborted',
    })
  })
})
