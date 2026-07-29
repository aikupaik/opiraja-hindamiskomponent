export type AdminSession = {
  subject: string
  capabilities: string[]
  max_graph_nodes: number
  diagnostic_max_events: number
  diagnostic_ttl_seconds: number
  source_max_bytes: number
  source_max_pdf_pages: number
  source_max_text_chars: number
}

export type CourseChoice = {
  value: string
  title: string
  label: string
}

export type SourceMaterial = {
  id: number
  course: string
  title: string
  source_url: string | null
  content: string | null
  content_preview: string
  added_at: string | null
}

export type YgRule = {
  id: number
  course: string
  description: string
  example: unknown
}

export type ItemStatus = 'draft' | 'usable' | 'review' | 'archived'
export type SaveMode = 'create_copy' | 'update_existing'

export type AdminItem = {
  yp_id: number
  course: string
  graph_node: string
  parent_graph_node: string | null
  cognitive_level: string
  instruction: string
  prompt: string
  stimulus: string | null
  answer_key: string
  distractor_1: string | null
  distractor_2: string | null
  distractor_3: string | null
  score: number
  irt_a: number
  irt_b: number
  beta_error: number
  guess_probability: number
  status: ItemStatus
  usage_count: number
  last_used_at: string | null
  created_at: string | null
  updated_at: string | null
}

export type EditableItem = Pick<
  AdminItem,
  | 'instruction'
  | 'prompt'
  | 'stimulus'
  | 'answer_key'
  | 'distractor_1'
  | 'distractor_2'
  | 'distractor_3'
  | 'status'
  | 'irt_a'
  | 'irt_b'
  | 'beta_error'
  | 'guess_probability'
>

export type ItemPage = {
  items: AdminItem[]
  total: number
  limit: number
  offset: number
}

export type Question = {
  submission_id: string
  item_id: number
  instruction: string
  prompt: string
  stimulus: string | null
  options: { id: string; text: string }[]
}

export type Feedback = {
  already_mastered: string[]
  learn_next: string[]
  review: string[]
  summary: string | null
  confidence_limited: boolean
}

export type PlayerView =
  | { status: 'preparing' }
  | { status: 'active'; question: Question }
  | { status: 'completed'; feedback: Feedback }

export type CreateTestResult = {
  test_id: string
  status: 'active' | 'preparing'
  player_url: string
  missing_nodes: string[]
}

export type DiagnosticEvent = {
  sequence: number
  timestamp: string
  source: string
  level: string
  type: string
  request_id: string | null
  test_id: string | null
  payload: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type RequestOptions = Omit<RequestInit, 'headers'> & {
  key: string
  experimentId?: string
  headers?: HeadersInit
}

export type ApiResponse<T> = {
  data: T
  status: number
  headers: Headers
  requestId: string | null
}

export async function apiResponse<T>(
  path: string,
  options: RequestOptions,
): Promise<ApiResponse<T>> {
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${options.key}`)
  if (options.experimentId) {
    headers.set('X-Experiment-ID', options.experimentId)
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...options, headers })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const envelope =
      body && typeof body === 'object' && 'error' in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : undefined
    throw new ApiError(
      response.status,
      envelope?.code ?? 'request_failed',
      envelope?.message ?? `Request failed (${response.status}).`,
    )
  }
  return {
    data: body as T,
    status: response.status,
    headers: response.headers,
    requestId: response.headers.get('X-Request-ID'),
  }
}

export async function api<T>(
  path: string,
  options: RequestOptions,
): Promise<T> {
  return (await apiResponse<T>(path, options)).data
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value)
}

export function errorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return ''
  }
  return error instanceof Error ? error.message : 'Unexpected request failure.'
}

export async function streamDiagnostics(
  key: string,
  experimentId: string,
  onEvent: (event: DiagnosticEvent) => void,
  signal: AbortSignal,
  afterSequence = 0,
): Promise<void> {
  let lastSequence = afterSequence
  while (!signal.aborted) {
    const response = await fetch(
      `/api/v1/admin/experiments/${encodeURIComponent(experimentId)}/events?after=${lastSequence}`,
      {
        headers: {
          Authorization: `Bearer ${key}`,
          Accept: 'text/event-stream',
        },
        signal,
      },
    )
    if (!response.ok || !response.body) {
      throw new ApiError(
        response.status,
        'diagnostic_stream_failed',
        'Diagnostic stream could not be opened.',
      )
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (!signal.aborted) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const dataLine = frame
          .split('\n')
          .find((line) => line.startsWith('data: '))
        if (!dataLine) continue
        const event = JSON.parse(dataLine.slice(6)) as DiagnosticEvent
        lastSequence = Math.max(lastSequence, event.sequence)
        onEvent(event)
      }
    }
    if (!signal.aborted) {
      await new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, 750)
        signal.addEventListener(
          'abort',
          () => {
            window.clearTimeout(timer)
            resolve()
          },
          { once: true },
        )
      })
    }
  }
}
