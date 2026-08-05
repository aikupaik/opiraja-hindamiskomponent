export type ApiErrorKind = 'aborted' | 'network' | 'http' | 'malformed'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly requestId: string | null
  readonly code: string | null

  constructor(
    kind: ApiErrorKind,
    options: {
      status?: number
      requestId?: string | null
      code?: string | null
      cause?: unknown
    } = {},
  ) {
    super('API request failed', { cause: options.cause })
    this.name = 'ApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.requestId = options.requestId ?? null
    this.code = options.code ?? null
  }
}

export interface CredentialSource {
  getCredential(): string | null
}

export type RequestAuthentication =
  | { mode: 'none' }
  | { mode: 'authenticated' }
  | { mode: 'credential-validation'; credential: string }

export type ApiRequestOptions = Omit<RequestInit, 'body' | 'headers'> & {
  authentication?: RequestAuthentication
  body?: BodyInit | null
  headers?: HeadersInit
  json?: unknown
}

export type ApiResponse<T> = {
  data: T
  status: number
  headers: Headers
  requestId: string | null
}

export type ApiClient = {
  request(path: string, options?: ApiRequestOptions): Promise<Response>
  json<T>(path: string, options?: ApiRequestOptions): Promise<ApiResponse<T>>
}

export function createApiClient(options: {
  credentialSource: CredentialSource
  fetcher?: typeof fetch
  onAuthenticatedUnauthorized?: (error: ApiError) => void
}): ApiClient {
  const configuredFetcher = options.fetcher

  async function request(
    path: string,
    requestOptions: ApiRequestOptions = {},
  ): Promise<Response> {
    const { authentication = { mode: 'authenticated' }, json, ...init } =
      requestOptions
    if (json !== undefined && init.body !== undefined) {
      throw new TypeError('Use either json or body, not both.')
    }

    const headers = new Headers(init.headers)
    const credential =
      authentication.mode === 'credential-validation'
        ? authentication.credential
        : authentication.mode === 'authenticated'
          ? options.credentialSource.getCredential()
          : null
    if (credential) headers.set('Authorization', `Bearer ${credential}`)
    if (json !== undefined) headers.set('Content-Type', 'application/json')

    let response: Response
    try {
      response = await (configuredFetcher ?? fetch)(path, {
        ...init,
        headers,
        ...(json !== undefined ? { body: JSON.stringify(json) } : {}),
      })
    } catch (error) {
      if (init.signal?.aborted || isAbortError(error)) {
        throw new ApiError('aborted', { cause: error })
      }
      throw new ApiError('network', { cause: error })
    }

    if (!response.ok) {
      const error = await decodeHttpError(response)
      if (
        response.status === 401 &&
        authentication.mode === 'authenticated' &&
        credential
      ) {
        options.onAuthenticatedUnauthorized?.(error)
      }
      throw error
    }
    return response
  }

  async function jsonRequest<T>(
    path: string,
    requestOptions: ApiRequestOptions = {},
  ): Promise<ApiResponse<T>> {
    const headers = new Headers(requestOptions.headers)
    headers.set('Accept', 'application/json')
    const response = await request(path, { ...requestOptions, headers })
    const requestId = response.headers.get('X-Request-ID')
    const data = await decodeJson(response, requestId)
    return { data: data as T, status: response.status, headers: response.headers, requestId }
  }

  return { request, json: jsonRequest }
}

async function decodeHttpError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID')
  let body: unknown = null
  try {
    body = await decodeJson(response.clone(), requestId)
  } catch {
    // HTTP status remains authoritative when an intermediary returns non-JSON.
  }
  return new ApiError('http', {
    status: response.status,
    requestId,
    code: applicationErrorCode(body),
  })
}

async function decodeJson(
  response: Response,
  requestId: string | null,
): Promise<unknown> {
  const contentType = response.headers.get('Content-Type') ?? ''
  const text = await response.text()
  if (!text || !contentType.toLowerCase().includes('application/json')) {
    throw new ApiError('malformed', { status: response.status, requestId })
  }
  try {
    return JSON.parse(text) as unknown
  } catch (error) {
    throw new ApiError('malformed', {
      status: response.status,
      requestId,
      cause: error,
    })
  }
}

function applicationErrorCode(value: unknown): string | null {
  if (!isRecord(value) || !isRecord(value.error)) return null
  return typeof value.error.code === 'string' &&
    typeof value.error.message === 'string'
    ? value.error.code
    : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
