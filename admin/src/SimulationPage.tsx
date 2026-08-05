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
          <p className="eyebrow">Manual end-to-end laboratory</p>
          <h1>Assessment simulation</h1>
          <p>
            Drive the real OR and player boundaries with experiment-scoped
            diagnostics.
          </p>
        </div>
        {experimentId && (
          <div className="experiment-badge">
            <span>Experiment</span>
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
            submitLabel={runState === 'idle' ? 'Run experiment' : 'Run again'}
            status={<span className={`run-state state-${runState}`}>{runState}</span>}
            onSubmit={runExperiment}
            actions={
              <>
              <button type="button" className="quiet" onClick={cancel} disabled={!running}>
                Cancel
              </button>
              <button type="button" className="quiet" onClick={reset}>
                Reset
              </button>
              </>
            }
          />

          {(runState !== 'idle' || view) && (
            <section className="panel player-card">
              <div className="section-heading">
                <div>
                  <h2>Simulated player</h2>
                  <p>{testId ? `test_id ${testId}` : 'Creating test…'}</p>
                </div>
              </div>
              {runState === 'creating' && (
                <div className="empty">Creating assessment through the OR API…</div>
              )}
              {runState === 'preparing' && (
                <div className="preparing-indicator">
                  <span />
                  <div>
                    <strong>Inventory is preparing</strong>
                    <p>Polling at the backend-provided Retry-After cadence.</p>
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
                  <p className="eyebrow">Final feedback</p>
                  <h3>{view.feedback.summary ?? 'Assessment completed.'}</h3>
                  <FeedbackGroup
                    label="Already mastered"
                    values={view.feedback.already_mastered}
                  />
                  <FeedbackGroup
                    label="Learn next"
                    values={view.feedback.learn_next}
                  />
                  <FeedbackGroup label="Review" values={view.feedback.review} />
                  {view.feedback.confidence_limited && (
                    <p className="confidence-note">
                      Result confidence was limited by the stopping condition.
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
              <strong>Experiment terminal</strong>
            </div>
            <span>{visibleEvents.length} events</span>
          </div>
          <div className="terminal-body" ref={terminalRef}>
            {visibleEvents.length === 0 ? (
              <p className="terminal-empty">
                Diagnostics will appear here after an experiment begins.
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
          <footer>
            Process-local · expires after inactivity · no persistence
          </footer>
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
          <p className="eyebrow">Ephemeral export</p>
          <h2 id="report-heading">Simulation report</h2>
          <p>Research evidence and developer performance diagnostics.</p>
        </div>
        {state.status === 'loaded' && (
          <div className="report-badges">
            <span className={`report-badge ${state.report.completion_state}`}>
              {state.report.completion_state}
            </span>
            <span
              className={`report-badge ${
                state.report.data_quality_warnings.length ? 'warning' : 'clean'
              }`}
            >
              {state.report.data_quality_warnings.length
                ? `${state.report.data_quality_warnings.length} warnings`
                : 'data complete'}
            </span>
          </div>
        )}
      </div>
      {state.status === 'loading' && (
        <div className="report-loading">Compiling retained diagnostics…</div>
      )}
      {state.status === 'failed' && (
        <div className="report-error">
          <p>{state.message || 'The report could not be generated.'}</p>
          <button type="button" className="quiet" onClick={retry}>
            Retry report
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
        <ReportMetric label="Run status" value={report.run_status} />
        <ReportMetric
          label="Responses"
          value={String(summary.response_count)}
        />
        <ReportMetric
          label="Accuracy"
          value={
            summary.overall_accuracy === null
              ? '—'
              : `${(summary.overall_accuracy * 100).toFixed(1)}%`
          }
        />
        <ReportMetric
          label="Stop reason"
          value={summary.stopping_reason ?? 'Incomplete'}
        />
        <ReportMetric
          label="API median"
          value={
            latency.median_ms === null
              ? '—'
              : `${latency.median_ms.toFixed(1)} ms`
          }
        />
        <ReportMetric
          label="Last stage"
          value={report.developer.last_successful_stage}
        />
      </div>
      {summary.node_path.length > 0 && (
        <div className="report-path">
          <span>Adaptive path</span>
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
          Download HTML report
        </button>
        <button
          type="button"
          className="quiet"
          onClick={() => downloadReportJson(report)}
        >
          Download JSON data
        </button>
      </div>
      <p className="report-retention">
        Generated from process-local diagnostics. Download to retain this
        report beyond the diagnostic TTL or a backend restart.
      </p>
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
