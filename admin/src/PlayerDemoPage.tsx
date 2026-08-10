import { useEffect, useRef, useState } from 'react'
import {
  api,
  apiResponse,
  errorMessage,
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
  courses: CourseChoice[]
  maxGraphNodes: number
}

const POLL_INTERVAL_MS = 3000
const demoStateLabels: Record<DemoState, string> = {
  idle: 'Ootel',
  creating: 'Loon testi',
  monitoring: 'Jälgin',
  completed: 'Lõpetatud',
  failed: 'Ebaõnnestus',
  paused: 'Peatatud',
  poll_error: 'Jälgimine ebaõnnestus',
}
const testStatusLabels = {
  preparing: 'Ettevalmistamisel',
  active: 'Aktiivne',
  completed: 'Lõpetatud',
  failed: 'Ebaõnnestus',
} as const

export function PlayerDemoPage({ courses, maxGraphNodes }: Props) {
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
        method: 'POST',
        signal: controller.signal,
        json: payload,
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
          { signal: controller.signal },
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
      setCopyMessage('Testimängija URL on kopeeritud.')
    } catch {
      setCopyMessage('URL-i ei saanud kopeerida. Vali ja kopeeri see käsitsi.')
    }
  }

  const stateLabel =
    state === 'monitoring'
      ? status
        ? testStatusLabels[status.status]
        : demoStateLabels.monitoring
      : demoStateLabels[state]
  const stateClass = state === 'monitoring' ? status?.status ?? state : state

  return (
    <main className="page player-demo-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Testimängija eelvaade</p>
          <h1>Testimängija</h1>
        </div>
      </div>
      {error && <div className="notice error">{error}</div>}

      <TestDefinitionForm
        courses={courses}
        maxGraphNodes={maxGraphNodes}
        disabled={formDisabled}
        submitLabel={state === 'creating' ? 'Loon…' : 'Loo testimängija test'}
        status={<span className={`run-state state-${stateClass}`}>{stateLabel}</span>}
        onSubmit={createTest}
        actions={
          created ? (
            <>
              {state === 'monitoring' && (
                <button type="button" className="quiet" onClick={pauseMonitoring}>
                  Peata jälgimine
                </button>
              )}
              {(state === 'paused' || state === 'poll_error') && (
                <button
                  type="button"
                  className="quiet"
                  onClick={() => startMonitoring(created.test_id)}
                >
                  Proovi jälgimist uuesti
                </button>
              )}
              <button type="button" className="quiet" onClick={reset}>
                Loo uus test
              </button>
            </>
          ) : undefined
        }
      />

      {created && playerUrl && (
        <section className="panel player-launch-card" aria-labelledby="player-link-heading">
          <div className="section-heading">
            <div>
              <h2 id="player-link-heading">Testimängija link</h2>
              <p>test_id {created.test_id}</p>
            </div>
            <span className={`run-state state-${stateClass}`}>{stateLabel}</span>
          </div>
          <div className="player-link-row">
            <a href={playerUrl} target="_blank" rel="noopener noreferrer">
              {playerUrl}
            </a>
            <button type="button" className="quiet" onClick={() => void copyPlayerUrl()}>
              Kopeeri
            </button>
            <a className="button-link primary" href={playerUrl} target="_blank" rel="noopener noreferrer">
              Ava uuel vahelehel
            </a>
          </div>
          {copyMessage && <p className="copy-status" aria-live="polite">{copyMessage}</p>}
          {state === 'monitoring' && (
            <div className="preparing-indicator" aria-live="polite">
              <span />
              <div>
                <strong>Ootan testimängijat</strong>
              </div>
            </div>
          )}
          {state === 'paused' && (
            <div className="notice">Jälgimine on peatatud. Test on endiselt saadaval.</div>
          )}
          {status?.status === 'failed' && (
            <div className="notice error">Test lõppes ebaõnnestunult.</div>
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
      <p className="eyebrow">Lõplik tagasiside</p>
      <h3>{feedback.summary ?? 'Test on lõpetatud.'}</h3>
      <FeedbackList label="Juba oskad" values={feedback.already_mastered} />
      <FeedbackList label="Õpi järgmisena" values={feedback.learn_next} />
      <FeedbackList label="Korda üle" values={feedback.review} />
      {feedback.confidence_limited && (
        <p className="confidence-note">
          Tulemuse usaldusväärsust piiras peatumise tingimus.
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
        <p>Puudub.</p>
      )}
    </section>
  )
}
