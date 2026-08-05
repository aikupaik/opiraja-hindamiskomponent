import { useEffect, useRef, useState } from 'react'
import {
  api,
  apiResponse,
  errorMessage,
  jsonBody,
  type CourseChoice,
  type CreateTestPayload,
  type CreateTestResult,
  type Feedback,
  type TestStatus,
} from './api'
import { TestDefinitionForm } from './TestDefinitionForm'

type DemoState =
  | 'idle'
  | 'creating'
  | 'monitoring'
  | 'completed'
  | 'failed'
  | 'paused'
  | 'poll_error'

type Props = {
  accessKey: string
  courses: CourseChoice[]
  maxGraphNodes: number
}

const POLL_INTERVAL_MS = 3000

export function PlayerDemoPage({ accessKey, courses, maxGraphNodes }: Props) {
  const [state, setState] = useState<DemoState>('idle')
  const [created, setCreated] = useState<CreateTestResult | null>(null)
  const [status, setStatus] = useState<TestStatus | null>(null)
  const [error, setError] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const controllerRef = useRef<AbortController | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => stopRequests, [])

  const playerUrl = created
    ? new URL(created.player_url, window.location.origin).href
    : null
  const formDisabled = state !== 'idle'

  function stopRequests() {
    controllerRef.current?.abort()
    controllerRef.current = null
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  async function createTest(payload: CreateTestPayload) {
    stopRequests()
    const controller = new AbortController()
    controllerRef.current = controller
    setState('creating')
    setCreated(null)
    setStatus(null)
    setError('')
    setCopyMessage('')
    try {
      const response = await apiResponse<CreateTestResult>('/api/v1/tests', {
        key: accessKey,
        method: 'POST',
        signal: controller.signal,
        body: jsonBody(payload),
      })
      if (controller.signal.aborted) return
      setCreated(response.data)
      setStatus({ status: response.data.status })
      startMonitoring(response.data.test_id)
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(errorMessage(caught))
        setState('idle')
      }
    }
  }

  function startMonitoring(testId: string) {
    stopRequests()
    const controller = new AbortController()
    controllerRef.current = controller
    setError('')
    setState('monitoring')

    const poll = async () => {
      try {
        const next = await api<TestStatus>(
          `/api/v1/tests/${encodeURIComponent(testId)}`,
          { key: accessKey, signal: controller.signal },
        )
        if (controller.signal.aborted) return
        setStatus(next)
        if (next.status === 'completed' || next.status === 'failed') {
          controllerRef.current = null
          setState(next.status)
          return
        }
        timerRef.current = setTimeout(() => {
          timerRef.current = null
          void poll()
        }, POLL_INTERVAL_MS)
      } catch (caught) {
        if (!controller.signal.aborted) {
          controllerRef.current = null
          setError(errorMessage(caught))
          setState('poll_error')
        }
      }
    }

    void poll()
  }

  function pauseMonitoring() {
    stopRequests()
    setState('paused')
  }

  function reset() {
    stopRequests()
    setCreated(null)
    setStatus(null)
    setError('')
    setCopyMessage('')
    setState('idle')
  }

  async function copyPlayerUrl() {
    if (!playerUrl) return
    try {
      await navigator.clipboard.writeText(playerUrl)
      setCopyMessage('Player URL copied.')
    } catch {
      setCopyMessage('Could not copy the URL. Select and copy it manually.')
    }
  }

  const stateLabel =
    state === 'monitoring' ? status?.status ?? 'monitoring' : state

  return (
    <main className="page player-demo-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">External OR request preview</p>
          <h1>Test player demo</h1>
          <p>
            Create a test, open the real learner player in another tab, and
            watch the OR status endpoint for completion.
          </p>
        </div>
      </div>
      {error && <div className="notice error">{error}</div>}

      <TestDefinitionForm
        courses={courses}
        maxGraphNodes={maxGraphNodes}
        disabled={formDisabled}
        submitLabel={state === 'creating' ? 'Creating…' : 'Create player test'}
        status={<span className={`run-state state-${stateLabel}`}>{stateLabel}</span>}
        onSubmit={createTest}
        actions={
          created ? (
            <>
              {state === 'monitoring' && (
                <button type="button" className="quiet" onClick={pauseMonitoring}>
                  Stop monitoring
                </button>
              )}
              {(state === 'paused' || state === 'poll_error') && (
                <button
                  type="button"
                  className="quiet"
                  onClick={() => startMonitoring(created.test_id)}
                >
                  Retry monitoring
                </button>
              )}
              <button type="button" className="quiet" onClick={reset}>
                Create another test
              </button>
            </>
          ) : undefined
        }
      />

      {created && playerUrl && (
        <section className="panel player-launch-card" aria-labelledby="player-link-heading">
          <div className="section-heading">
            <div>
              <h2 id="player-link-heading">Player link</h2>
              <p>test_id {created.test_id}</p>
            </div>
            <span className={`run-state state-${stateLabel}`}>{stateLabel}</span>
          </div>
          <div className="player-link-row">
            <a href={playerUrl} target="_blank" rel="noopener noreferrer">
              {playerUrl}
            </a>
            <button type="button" className="quiet" onClick={() => void copyPlayerUrl()}>
              Copy
            </button>
            <a className="button-link primary" href={playerUrl} target="_blank" rel="noopener noreferrer">
              Open in new tab
            </a>
          </div>
          {copyMessage && <p className="copy-status" aria-live="polite">{copyMessage}</p>}
          {state === 'monitoring' && (
            <div className="preparing-indicator" aria-live="polite">
              <span />
              <div>
                <strong>Waiting for the player</strong>
                <p>Checking OR status every three seconds while this page is open.</p>
              </div>
            </div>
          )}
          {state === 'paused' && (
            <div className="notice">Monitoring is paused. The player test remains available.</div>
          )}
          {status?.status === 'failed' && (
            <div className="notice error">The assessment ended in a failed state.</div>
          )}
          {status?.status === 'completed' && <CompletionFeedback feedback={status.feedback} />}
        </section>
      )}
    </main>
  )
}

function CompletionFeedback({ feedback }: { feedback: Feedback }) {
  return (
    <div className="feedback player-demo-feedback">
      <p className="eyebrow">Final OR response</p>
      <h3>{feedback.summary ?? 'Assessment completed.'}</h3>
      <FeedbackList label="Already mastered" values={feedback.already_mastered} />
      <FeedbackList label="Learn next" values={feedback.learn_next} />
      <FeedbackList label="Review" values={feedback.review} />
      {feedback.confidence_limited && (
        <p className="confidence-note">
          Result confidence was limited by the stopping condition.
        </p>
      )}
    </div>
  )
}

function FeedbackList({ label, values }: { label: string; values: string[] }) {
  return (
    <section>
      <h4>{label}</h4>
      {values.length ? (
        <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul>
      ) : (
        <p>None.</p>
      )}
    </section>
  )
}
