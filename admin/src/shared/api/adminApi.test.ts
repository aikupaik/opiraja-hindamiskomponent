import { describe, expect, it, vi } from 'vitest'
import { ApiError, createApiClient } from '@opiraja/frontend-api'
import { errorMessage } from './adminApi'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': 'request-42',
    },
  })
}

describe('shared frontend transport', () => {
  it('serializes JSON and constructs the bearer header centrally', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    const client = createApiClient({
      credentialSource: { getCredential: () => 'credential' },
      fetcher,
    })

    await client.json('/example', { method: 'POST', json: { value: 3 } })

    const init = fetcher.mock.calls[0][1] as RequestInit
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer credential')
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ value: 3 }))
  })

  it('leaves multipart content-type generation to the browser', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    const client = createApiClient({
      credentialSource: { getCredential: () => 'credential' },
      fetcher,
    })
    const form = new FormData()
    form.set('course', 'FÜS101')

    await client.json('/upload', { method: 'POST', body: form })

    const init = fetcher.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Content-Type')).toBeNull()
    expect(init.body).toBe(form)
  })

  it('preserves request diagnostics without exposing envelope messages', async () => {
    const client = createApiClient({
      credentialSource: { getCredential: () => 'credential' },
      fetcher: vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'private_code', message: 'Backend detail' } },
          503,
        ),
      ),
    })

    const error = await client.json('/example').catch((caught: unknown) => caught)
    expect(error).toMatchObject({
      kind: 'http',
      status: 503,
      code: 'private_code',
      requestId: 'request-42',
    })
    expect(errorMessage(error)).toBe(
      'Päringut ei saanud täita. Viitenumber: request-42.',
    )
    expect(errorMessage(error)).not.toContain('Backend detail')
  })

  it('notifies only for 401s on already-authenticated requests', async () => {
    const unauthorized = vi.fn()
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({ error: { code: 'unauthorized', message: 'No' } }, 401),
    )
    const client = createApiClient({
      credentialSource: { getCredential: () => 'stored' },
      fetcher,
      onAuthenticatedUnauthorized: unauthorized,
    })

    await expect(client.json('/authenticated')).rejects.toBeInstanceOf(ApiError)
    await expect(
      client.json('/login', {
        authentication: {
          mode: 'credential-validation',
          credential: 'candidate',
        },
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(unauthorized).toHaveBeenCalledTimes(1)
    expect(
      new Headers(fetcher.mock.calls[1][1].headers).get('Authorization'),
    ).toBe('Bearer candidate')
  })

  it('normalizes abort and network failures', async () => {
    const controller = new AbortController()
    controller.abort()
    const aborted = createApiClient({
      credentialSource: { getCredential: () => null },
      fetcher: vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')),
    })
    await expect(
      aborted.json('/example', { signal: controller.signal }),
    ).rejects.toMatchObject({ kind: 'aborted' })

    const offline = createApiClient({
      credentialSource: { getCredential: () => null },
      fetcher: vi.fn().mockRejectedValue(new TypeError('offline')),
    })
    await expect(offline.json('/example')).rejects.toMatchObject({
      kind: 'network',
    })
  })
})
