import { useEffect, useRef, useState } from 'react'
import {
  api,
  apiResponse,
  errorMessage,
  isVisibleDiagnostic,
  streamDiagnostics,
  type CourseChoice,
  type CreateTestPayload,
  type CreateTestResult,
  type DiagnosticEvent,
  type PlayerView,
} from './api'
import { TestDefinitionForm } from './TestDefinitionForm'
import {
  downloadReportHtml,
  downloadReportJson,
  reportStatusLabels,
  type ExperimentReport,
} from './report'
import { createUuid } from './uuid'

type RunState =
  | 'idle'
  | 'creating'
  | 'preparing'
  | 'active'
  | 'completed'
  | 'failed'
  | 'cancelled'
type ReportState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; report: ExperimentReport }
  | { status: 'failed'; message: string }

type Props = {
  courses: CourseChoice[]
  maxGraphNodes: number
}

const runStateLabels: Record<RunState, string> = {
  idle: 'Ootel',
  creating: 'Loon testi',
  preparing: 'Ettevalmistamisel',
  active: 'Aktiivne',
  completed: 'Lõpetatud',
  failed: 'Ebaõnnestus',
  cancelled: 'Tühistatud',
}
const completionStateLabels = { completed: 'Lõpetatud', partial: 'Osaline' } as const

export function SimulationPage({
  courses,
  maxGraphNodes,
}: Props) {
  const [runState, setRunState] = useState<RunState>('idle')
  const [experimentId, setExperimentId] = useState<string | null>(null)
  const [testId, setTestId] = useState<string | null>(null)
  const [view, setView] = useState<PlayerView | null>(null)
  const [events, setEvents] = useState<DiagnosticEvent[]>([])
  const [reportState, setReportState] = useState<ReportState>({ status: 'idle' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const terminalRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    terminalRef.current?.scrollTo({
      top: terminalRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [events])

  useEffect(() => () => controllerRef.current?.abort(), [])

  useEffect(() => {
    if (
      !experimentId ||
      !['completed', 'failed', 'cancelled'].includes(runState)
    ) {
      return
    }
    let current = true
    setReportState({ status: 'loading' })
    void api<ExperimentReport>(
      `/api/v1/admin/experiments/${encodeURIComponent(experimentId)}/report`,
      {},
    )
      .then((report) => {
        if (current) setReportState({ status: 'loaded', report })
      })
      .catch((caught: unknown) => {
        if (current) {
          setReportState({ status: 'failed', message: errorMessage(caught) })
        }
      })
    return () => {
      current = false
    }
  }, [experimentId, runState])

  const visibleEvents = events.filter(isVisibleDiagnostic)
  const running = !['idle', 'completed', 'failed', 'cancelled'].includes(
    runState,
  )

  async function runExperiment(payload: CreateTestPayload) {
    setError('')
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const nextExperimentId = createUuid()
    setExperimentId(nextExperimentId)
    setTestId(null)
    setView(null)
    setEvents([])
    setReportState({ status: 'idle' })
    setRunState('creating')

    void streamDiagnostics(
      nextExperimentId,
      (diagnostic) =>
        setEvents((current) => [...current.slice(-499), diagnostic]),
      controller.signal,
    ).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(caught))
    })

    try {
      const created = await apiResponse<CreateTestResult>('/api/v1/tests', {
        experimentId: nextExperimentId,
        method: 'POST',
        signal: controller.signal,
        json: payload,
      })
      setTestId(created.data.test_id)
      await pollStart(created.data.test_id, nextExperimentId, controller)
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(errorMessage(caught))
        setRunState('failed')
      }
    }
  }

  async function pollStart(
    currentTestId: string,
    currentExperimentId: string,
    controller: AbortController,
  ) {
    while (!controller.signal.aborted) {
      const response = await apiResponse<PlayerView>(
        `/api/v1/player/tests/${currentTestId}/start`,
        {
          experimentId: currentExperimentId,
          method: 'POST',
          signal: controller.signal,
        },
      )
      setView(response.data)
      if (response.data.status === 'preparing') {
        setRunState('preparing')
        const seconds = Number(response.headers.get('Retry-After') ?? '3')
        await abortableDelay(
          Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 3000,
          controller.signal,
        )
        continue
      }
      setRunState(response.data.status)
      return
    }
  }

  async function submitAnswer(optionId: string) {
    if (
      submitting ||
      !testId ||
      !experimentId ||
      view?.status !== 'active'
    ) {
      return
    }
    const controller = controllerRef.current
    if (!controller) return
    setSubmitting(true)
    setError('')
    try {
      const response = await apiResponse<PlayerView>(
        `/api/v1/player/tests/${testId}/answers`,
        {
          experimentId,
          method: 'POST',
          signal: controller.signal,
          json: {
            submission_id: view.question.submission_id,
            option_id: optionId,
          },
        },
      )
      setView(response.data)
      setRunState(response.data.status)
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(errorMessage(caught))
        setRunState('failed')
      }
    } finally {
      setSubmitting(false)
    }
  }

  function cancel() {
    controllerRef.current?.abort()
    controllerRef.current = null
    if (running) setRunState('cancelled')
  }

  function reset() {
    cancel()
    setExperimentId(null)
    setTestId(null)
    setView(null)
    setEvents([])
    setReportState({ status: 'idle' })
    setError('')
    setRunState('idle')
    setSubmitting(false)
  }

  return (
    <main className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Käsitsi käivitatav simulatsioon</p>
          <h1>Testi simulatsioon</h1>
        </div>
        {experimentId && (
          <div className="experiment-badge">
            <span>Katse</span>
            <code>{experimentId}</code>
          </div>
        )}
      </div>
      {error && <div className="notice error">{error}</div>}

      <div className="simulation-layout">
        <section className="simulation-main">
          <TestDefinitionForm
            courses={courses}
            maxGraphNodes={maxGraphNodes}
            disabled={running}
            submitLabel={runState === 'idle' ? 'Käivita katse' : 'Käivita uuesti'}
            status={<span className={`run-state state-${runState}`}>{runStateLabels[runState]}</span>}
            onSubmit={runExperiment}
            actions={
              <>
              <button type="button" className="quiet" onClick={cancel} disabled={!running}>
                Tühista
              </button>
              <button type="button" className="quiet" onClick={reset}>
                Lähtesta
              </button>
              </>
            }
          />

          {(runState !== 'idle' || view) && (
            <section className="panel player-card">
              <div className="section-heading">
                <div>
                  <h2>Simuleeritud testimängija</h2>
                  <p>{testId ? `test_id ${testId}` : 'Loon testi…'}</p>
                </div>
              </div>
              {runState === 'creating' && (
                <div className="empty">Loon testi…</div>
              )}
              {runState === 'preparing' && (
                <div className="preparing-indicator">
                  <span />
                  <div>
                    <strong>Küsimuste kogu valmistub</strong>
                  </div>
                </div>
              )}
              {view?.status === 'active' && runState === 'active' && (
                <div className="question">
                  <p className="instruction">{view.question.instruction}</p>
                  {view.question.stimulus && (
                    <blockquote>{view.question.stimulus}</blockquote>
                  )}
                  <h3>{view.question.prompt}</h3>
                  <div className="options">
                    {view.question.options.map((option, index) => (
                      <button
                        type="button"
                        key={option.id}
                        disabled={submitting}
                        onClick={() => void submitAnswer(option.id)}
                      >
                        <span>{String.fromCharCode(65 + index)}</span>
                        {option.text}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {view?.status === 'completed' && (
                <div className="feedback">
                  <p className="eyebrow">Lõplik tagasiside</p>
                  <h3>{view.feedback.summary ?? 'Test on lõpetatud.'}</h3>
                  <FeedbackGroup
                    label="Juba oskad"
                    values={view.feedback.already_mastered}
                  />
                  <FeedbackGroup
                    label="Õpi järgmisena"
                    values={view.feedback.learn_next}
                  />
                  <FeedbackGroup label="Korda üle" values={view.feedback.review} />
                  {view.feedback.confidence_limited && (
                    <p className="confidence-note">
                      Tulemuse usaldusväärsust piiras peatumise tingimus.
                    </p>
                  )}
                </div>
              )}
            </section>
          )}

          {experimentId &&
            ['completed', 'failed', 'cancelled'].includes(runState) && (
              <ReportPanel
                state={reportState}
                retry={() => {
                  setReportState({ status: 'loading' })
                  void api<ExperimentReport>(
                    `/api/v1/admin/experiments/${encodeURIComponent(experimentId)}/report`,
                  )
                    .then((report) =>
                      setReportState({ status: 'loaded', report }),
                    )
                    .catch((caught: unknown) =>
                      setReportState({
                        status: 'failed',
                        message: errorMessage(caught),
                      }),
                    )
                }}
              />
            )}
        </section>

        <aside className="terminal panel">
          <div className="terminal-header">
            <div>
              <span className="terminal-lights">● ● ●</span>
              <strong>Katse sündmused</strong>
            </div>
            <span>{visibleEvents.length} sündmust</span>
          </div>
          <div className="terminal-body" ref={terminalRef}>
            {visibleEvents.length === 0 ? (
              <p className="terminal-empty">
                Sündmused ilmuvad siia pärast katse käivitamist.
              </p>
            ) : (
              visibleEvents.map((event) => (
                <article key={event.sequence} className={`log-${event.level}`}>
                  <header>
                    <span>{String(event.sequence).padStart(3, '0')}</span>
                    <time>
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </time>
                    <strong>{event.source}</strong>
                    <em>{event.type}</em>
                  </header>
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                </article>
              ))
            )}
          </div>
        </aside>
      </div>
    </main>
  )
}

function ReportPanel({
  state,
  retry,
}: {
  state: ReportState
  retry: () => void
}) {
  return (
    <section className="panel report-panel" aria-labelledby="report-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Aruanne</p>
          <h2 id="report-heading">Simulatsiooniaruanne</h2>
        </div>
        {state.status === 'loaded' && (
          <div className="report-badges">
            <span className={`report-badge ${state.report.completion_state}`}>
              {completionStateLabels[state.report.completion_state]}
            </span>
            <span
              className={`report-badge ${
                state.report.data_quality_warnings.length ? 'warning' : 'clean'
              }`}
            >
              {state.report.data_quality_warnings.length
                ? `${state.report.data_quality_warnings.length} hoiatust`
                : 'andmed on täielikud'}
            </span>
          </div>
        )}
      </div>
      {state.status === 'loading' && (
        <div className="report-loading">Koostan aruannet…</div>
      )}
      {state.status === 'failed' && (
        <div className="report-error">
          <p>{state.message || 'Aruannet ei saanud koostada.'}</p>
          <button type="button" className="quiet" onClick={retry}>
            Proovi uuesti
          </button>
        </div>
      )}
      {state.status === 'loaded' && (
        <ReportPreview report={state.report} />
      )}
    </section>
  )
}

function ReportPreview({ report }: { report: ExperimentReport }) {
  const summary = report.research.summary
  const latency = report.developer.api_latency
  return (
    <div className="report-content">
      <p className="report-interpretation">
        {report.research.interpretation}
      </p>
      <div className="report-summary-grid">
        <ReportMetric
          label="Katse olek"
          value={reportStatusLabels[report.run_status] ?? report.run_status}
        />
        <ReportMetric
          label="Vastuseid"
          value={String(summary.response_count)}
        />
        <ReportMetric
          label="Täpsus"
          value={
            summary.overall_accuracy === null
              ? '—'
              : `${(summary.overall_accuracy * 100).toFixed(1)}%`
          }
        />
        <ReportMetric
          label="Peatumise põhjus"
          value={summary.stopping_reason ?? 'Puudulik'}
        />
        <ReportMetric
          label="API mediaan"
          value={
            latency.median_ms === null
              ? '—'
              : `${latency.median_ms.toFixed(1)} ms`
          }
        />
        <ReportMetric
          label="Viimane etapp"
          value={report.developer.last_successful_stage}
        />
      </div>
      {summary.node_path.length > 0 && (
        <div className="report-path">
          <span>Kohanduv rada</span>
          <p>{summary.node_path.join(' → ')}</p>
        </div>
      )}
      {report.data_quality_warnings.length > 0 && (
        <ul className="report-warnings">
          {report.data_quality_warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <div className="report-actions">
        <button
          type="button"
          className="primary"
          onClick={() => downloadReportHtml(report)}
        >
          Laadi HTML-aruanne alla
        </button>
        <button
          type="button"
          className="quiet"
          onClick={() => downloadReportJson(report)}
        >
          Laadi JSON-andmed alla
        </button>
      </div>
    </div>
  )
}

function ReportMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function FeedbackGroup({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="feedback-group">
      <span>{label}</span>
      <p>{values.length ? values.join(' · ') : '—'}</p>
    </div>
  )
}

function abortableDelay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds)
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}
