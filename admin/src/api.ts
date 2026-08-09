import {
  ApiError,
  createApiClient,
  type ApiRequestOptions,
  type ApiResponse,
} from '@opiraja/frontend-api'
import {
  adminCredentialSource,
  expireAdminCredential,
} from './credential'

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

export type KstConfiguration = {
  feedback_credible_mass: number
  reliability_floor: { minimum: number; multiplier: number; maximum: number }
  safety_cap: { minimum_above_floor: number; node_multiplier: number }
  schema_version: 1
  stop_confidence: number
}

export type KstConfigurationVersion = {
  id: string
  schema_version: number
  configuration: KstConfiguration
  configuration_hash: string
  created_by: string
  created_at: string
  is_active: boolean
  last_activated_by: string | null
  last_activated_at: string | null
}

export type KstConfigurationHistory = {
  active_version_id: string | null
  versions: KstConfigurationVersion[]
}

export type AdminLoginResponse = {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  session: AdminSession
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

export type TestRelation = { from: string; to: string }

export type CreateTestPayload = {
  user_id: string
  learning_path_id: string
  course: string
  goal: 'real_test' | 'trial_run'
  method: 'kst'
  cognitive_level: 'mõistab'
  nodes: string[]
  relations: TestRelation[]
}

export type TestStatus =
  | { status: 'preparing' }
  | { status: 'active' }
  | { status: 'completed'; feedback: Feedback }
  | { status: 'failed' }

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

export function isVisibleDiagnostic(event: DiagnosticEvent) {
  return event.type !== 'supabase_operation' && event.source !== 'supabase'
}

type RequestOptions = ApiRequestOptions & {
  experimentId?: string
}

export { ApiError }
export type { ApiResponse }

const client = createApiClient({
  credentialSource: adminCredentialSource,
  onAuthenticatedUnauthorized: expireAdminCredential,
})

export async function apiResponse<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const { experimentId, ...requestOptions } = options
  const headers = new Headers(options.headers)
  if (experimentId) {
    headers.set('X-Experiment-ID', experimentId)
  }
  return client.json<T>(path, { ...requestOptions, headers })
}

export async function api<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return (await apiResponse<T>(path, options)).data
}

export async function loginAdmin(
  accessKey: string,
  signal?: AbortSignal,
): Promise<AdminLoginResponse> {
  return (
    await client.json<AdminLoginResponse>('/api/v1/admin/login', {
      method: 'POST',
      authentication: { mode: 'none' },
      json: { access_key: accessKey },
      signal,
    })
  ).data
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === 'aborted') return ''
  const reference =
    error instanceof ApiError && error.requestId
      ? ` Reference: ${error.requestId}.`
      : ''
  return error instanceof ApiError && error.kind === 'network'
    ? `The service could not be reached.${reference}`
    : `The request could not be completed.${reference}`
}

export function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === 'aborted') return ''
  const reference =
    error instanceof ApiError && error.requestId
      ? ` Reference: ${error.requestId}.`
      : ''
  return `The credentials were not accepted.${reference}`
}

export async function streamDiagnostics(
  experimentId: string,
  onEvent: (event: DiagnosticEvent) => void,
  signal: AbortSignal,
  afterSequence = 0,
): Promise<void> {
  let lastSequence = afterSequence
  while (!signal.aborted) {
    const response = await client.request(
      `/api/v1/admin/experiments/${encodeURIComponent(experimentId)}/events?after=${lastSequence}`,
      {
        headers: { Accept: 'text/event-stream' },
        signal,
      },
    )
    if (!response.body) {
      throw new ApiError(
        'malformed',
        {
          status: response.status,
          requestId: response.headers.get('X-Request-ID'),
          code: 'diagnostic_stream_failed',
        },
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
