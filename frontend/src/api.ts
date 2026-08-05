import {
  permissiveCredentialSource,
  type CredentialSource,
} from './credential'

export interface QuestionOption {
  id: string
  text: string
}

export interface PlayerQuestion {
  submission_id: string
  item_id: number
  instruction: string
  prompt: string
  stimulus: string | null
  options: QuestionOption[]
}

export interface PlayerFeedback {
  already_mastered: string[]
  learn_next: string[]
  review: string[]
  summary: string | null
  confidence_limited: boolean
}

export interface PreparingResult {
  status: 'preparing'
  retryAfterSeconds: number
}

export interface ActiveResult {
  status: 'active'
  question: PlayerQuestion
}

export interface CompletedResult {
  status: 'completed'
  feedback: PlayerFeedback
}

export type StartResult = PreparingResult | ActiveResult | CompletedResult
export type AnswerResult = ActiveResult | CompletedResult

export interface SubmissionPayload {
  submission_id: string
  option_id: string
}

export type PlayerApiErrorKind =
  | 'aborted'
  | 'network'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'unavailable'
  | 'http'
  | 'malformed'

export class PlayerApiError extends Error {
  readonly kind: PlayerApiErrorKind
  readonly status: number | null
  readonly requestId: string | null
  readonly code: string | null

  constructor(
    kind: PlayerApiErrorKind,
    options: {
      status?: number
      requestId?: string | null
      code?: string | null
      cause?: unknown
    } = {},
  ) {
    super('Player API request failed', { cause: options.cause })
    this.name = 'PlayerApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.requestId = options.requestId ?? null
    this.code = options.code ?? null
  }
}

export interface PlayerApi {
  start(testId: string, signal: AbortSignal): Promise<StartResult>
  submit(
    testId: string,
    payload: SubmissionPayload,
    signal: AbortSignal,
  ): Promise<AnswerResult>
}

interface PlayerApiOptions {
  credentialSource?: CredentialSource
  fetcher?: typeof fetch
}

export function createPlayerApi(options: PlayerApiOptions = {}): PlayerApi {
  const credentialSource =
    options.credentialSource ?? permissiveCredentialSource
  const fetcher = options.fetcher ?? fetch

  async function request(
    path: string,
    signal: AbortSignal,
    payload?: SubmissionPayload,
  ): Promise<StartResult> {
    const headers = new Headers({ Accept: 'application/json' })
    const credential = credentialSource.getCredential()
    if (credential) {
      headers.set('Authorization', `Bearer ${credential}`)
    }
    if (payload) {
      headers.set('Content-Type', 'application/json')
    }

    let response: Response
    try {
      response = await fetcher(path, {
        method: 'POST',
        headers,
        signal,
        ...(payload ? { body: JSON.stringify(payload) } : {}),
      })
    } catch (error) {
      if (signal.aborted || isAbortError(error)) {
        throw new PlayerApiError('aborted', { cause: error })
      }
      throw new PlayerApiError('network', { cause: error })
    }

    const requestId = response.headers.get('X-Request-ID')
    let decoded: unknown
    try {
      decoded = await decodeJson(response, requestId)
    } catch (error) {
      if (!response.ok) {
        throw decodeHttpError(response.status, requestId, null)
      }
      throw error
    }
    if (!response.ok) {
      throw decodeHttpError(response.status, requestId, decoded)
    }
    if (response.status === 202) {
      if (!isPreparing(decoded)) {
        throw malformed(response.status, requestId)
      }
      return {
        status: 'preparing',
        retryAfterSeconds: parseRetryAfter(response.headers.get('Retry-After')),
      }
    }
    if (response.status !== 200) {
      throw new PlayerApiError('http', {
        status: response.status,
        requestId,
      })
    }
    if (isActive(decoded) || isCompleted(decoded)) {
      return decoded
    }
    throw malformed(response.status, requestId)
  }

  return {
    start: (testId, signal) =>
      request(`/api/v1/player/tests/${testId}/start`, signal),
    submit: async (testId, payload, signal) => {
      const result = await request(
        `/api/v1/player/tests/${testId}/answers`,
        signal,
        payload,
      )
      if (result.status === 'preparing') {
        throw malformed(202, null)
      }
      return result
    },
  }
}

async function decodeJson(
  response: Response,
  requestId: string | null,
): Promise<unknown> {
  const text = await response.text()
  if (!text) {
    throw malformed(response.status, requestId)
  }
  try {
    return JSON.parse(text) as unknown
  } catch (error) {
    throw new PlayerApiError('malformed', {
      status: response.status,
      requestId,
      cause: error,
    })
  }
}

function decodeHttpError(
  status: number,
  requestId: string | null,
  body: unknown,
): PlayerApiError {
  const code = applicationErrorCode(body)
  const kind: PlayerApiErrorKind =
    status === 403
      ? 'forbidden'
      : status === 404
        ? 'not_found'
        : status === 409
          ? 'conflict'
          : status === 422
            ? 'validation'
            : status === 503
              ? 'unavailable'
              : 'http'
  return new PlayerApiError(kind, { status, requestId, code })
}

function applicationErrorCode(value: unknown): string | null {
  if (!isRecord(value) || !isRecord(value.error)) return null
  return typeof value.error.code === 'string' &&
    typeof value.error.message === 'string'
    ? value.error.code
    : null
}

function isPreparing(value: unknown): value is { status: 'preparing' } {
  return isRecord(value) && value.status === 'preparing'
}

function isActive(value: unknown): value is ActiveResult {
  if (!isRecord(value) || value.status !== 'active' || !isRecord(value.question)) {
    return false
  }
  const question = value.question
  return (
    isUuid(question.submission_id) &&
    typeof question.item_id === 'number' &&
    Number.isInteger(question.item_id) &&
    typeof question.instruction === 'string' &&
    typeof question.prompt === 'string' &&
    (question.stimulus === null || typeof question.stimulus === 'string') &&
    Array.isArray(question.options) &&
    question.options.length >= 2 &&
    question.options.every(
      (option) =>
        isRecord(option) &&
        typeof option.id === 'string' &&
        option.id.length > 0 &&
        typeof option.text === 'string',
    )
  )
}

function isCompleted(value: unknown): value is CompletedResult {
  if (
    !isRecord(value) ||
    value.status !== 'completed' ||
    !isRecord(value.feedback)
  ) {
    return false
  }
  const feedback = value.feedback
  return (
    isStringArray(feedback.already_mastered) &&
    isStringArray(feedback.learn_next) &&
    isStringArray(feedback.review) &&
    (feedback.summary === null || typeof feedback.summary === 'string') &&
    typeof feedback.confidence_limited === 'boolean'
  )
}

function parseRetryAfter(value: string | null): number {
  if (value === null || !/^\d+$/.test(value)) return 3
  const seconds = Number(value)
  return Number.isSafeInteger(seconds) ? seconds : 3
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string')
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  )
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function malformed(status: number, requestId: string | null): PlayerApiError {
  return new PlayerApiError('malformed', { status, requestId })
}

export const playerApi = createPlayerApi()
