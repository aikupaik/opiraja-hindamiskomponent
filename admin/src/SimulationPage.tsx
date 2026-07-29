import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  apiResponse,
  errorMessage,
  jsonBody,
  streamDiagnostics,
  type CourseChoice,
  type CreateTestResult,
  type DiagnosticEvent,
  type PlayerView,
} from './api'

type Relation = { from: string; to: string }
type RunState = 'idle' | 'creating' | 'preparing' | 'active' | 'completed' | 'failed'

type Props = {
  accessKey: string
  courses: CourseChoice[]
  maxGraphNodes: number
}

export function SimulationPage({
  accessKey,
  courses,
  maxGraphNodes,
}: Props) {
  const [userId, setUserId] = useState('admin-simulation-user')
  const [learningPathId, setLearningPathId] = useState('manual-experiment')
  const [course, setCourse] = useState(courses[0]?.value ?? '')
  const [goal, setGoal] = useState<'real_test' | 'trial_run'>('trial_run')
  const [nodes, setNodes] = useState<string[]>([''])
  const [relations, setRelations] = useState<Relation[]>([])
  const [runState, setRunState] = useState<RunState>('idle')
  const [experimentId, setExperimentId] = useState<string | null>(null)
  const [testId, setTestId] = useState<string | null>(null)
  const [view, setView] = useState<PlayerView | null>(null)
  const [events, setEvents] = useState<DiagnosticEvent[]>([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const terminalRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!course && courses[0]) setCourse(courses[0].value)
  }, [course, courses])

  useEffect(() => {
    terminalRef.current?.scrollTo({
      top: terminalRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [events])

  useEffect(() => () => controllerRef.current?.abort(), [])

  const enteredNodes = nodes.map((node) => node.trim()).filter(Boolean)
  const running = !['idle', 'completed', 'failed'].includes(runState)

  function updateNode(index: number, value: string) {
    const next = nodes.map((node, nodeIndex) =>
      nodeIndex === index ? value : node,
    )
    setNodes(next)
    const valid = new Set(next.map((node) => node.trim()).filter(Boolean))
    setRelations((current) =>
      current.filter(
        (relation) => valid.has(relation.from) && valid.has(relation.to),
      ),
    )
  }

  function removeNode(index: number) {
    if (nodes.length === 1) return
    const removed = nodes[index]?.trim()
    setNodes(nodes.filter((_, nodeIndex) => nodeIndex !== index))
    setRelations((current) =>
      current.filter(
        (relation) => relation.from !== removed && relation.to !== removed,
      ),
    )
  }

  async function runExperiment(event: FormEvent) {
    event.preventDefault()
    setError('')
    const normalizedNodes = nodes.map((node) => node.trim()).filter(Boolean)
    if (!userId.trim() || !learningPathId.trim() || !course) {
      setError('User, learning path, and course are required.')
      return
    }
    if (
      normalizedNodes.length === 0 ||
      normalizedNodes.length > maxGraphNodes ||
      new Set(normalizedNodes).size !== normalizedNodes.length
    ) {
      setError(
        `Enter 1–${maxGraphNodes} unique, nonblank graph nodes.`,
      )
      return
    }
    if (
      relations.some(
        (relation) =>
          !normalizedNodes.includes(relation.from) ||
          !normalizedNodes.includes(relation.to) ||
          relation.from === relation.to,
      )
    ) {
      setError('Every relation needs two different entered nodes.')
      return
    }

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const nextExperimentId = crypto.randomUUID()
    setExperimentId(nextExperimentId)
    setTestId(null)
    setView(null)
    setEvents([])
    setRunState('creating')

    void streamDiagnostics(
      accessKey,
      nextExperimentId,
      (diagnostic) =>
        setEvents((current) => [...current.slice(-499), diagnostic]),
      controller.signal,
    ).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(caught))
    })

    try {
      const created = await apiResponse<CreateTestResult>('/api/v1/tests', {
        key: accessKey,
        experimentId: nextExperimentId,
        method: 'POST',
        signal: controller.signal,
        body: jsonBody({
          user_id: userId.trim(),
          learning_path_id: learningPathId.trim(),
          course,
          goal,
          method: 'kst',
          cognitive_level: 'mõistab',
          nodes: normalizedNodes,
          relations,
        }),
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
          key: accessKey,
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
          key: accessKey,
          experimentId,
          method: 'POST',
          signal: controller.signal,
          body: jsonBody({
            submission_id: view.question.submission_id,
            option_id: optionId,
          }),
        },
      )
      setView(response.data)
      setRunState(response.data.status)
    } catch (caught) {
      if (!controller.signal.aborted) setError(errorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  function cancel() {
    controllerRef.current?.abort()
    controllerRef.current = null
    if (running) setRunState('idle')
  }

  function reset() {
    cancel()
    setExperimentId(null)
    setTestId(null)
    setView(null)
    setEvents([])
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
          <form className="panel simulation-form" onSubmit={runExperiment}>
            <div className="section-heading">
              <div>
                <h2>Test definition</h2>
                <p>Method kst · cognitive level mõistab</p>
              </div>
              <span className={`run-state state-${runState}`}>{runState}</span>
            </div>
            <div className="field-row">
              <label>
                <span>User ID</span>
                <input
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                  disabled={running}
                />
              </label>
              <label>
                <span>Learning path ID</span>
                <input
                  value={learningPathId}
                  onChange={(event) => setLearningPathId(event.target.value)}
                  disabled={running}
                />
              </label>
            </div>
            <div className="field-row">
              <label>
                <span>Course</span>
                <select
                  value={course}
                  onChange={(event) => setCourse(event.target.value)}
                  disabled={running}
                >
                  <option value="">Select course</option>
                  {courses.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Goal</span>
                <select
                  value={goal}
                  onChange={(event) =>
                    setGoal(event.target.value as 'real_test' | 'trial_run')
                  }
                  disabled={running}
                >
                  <option value="real_test">Real test</option>
                  <option value="trial_run">Trial run</option>
                </select>
              </label>
            </div>

            <div className="dynamic-section">
              <div className="dynamic-heading">
                <div>
                  <h3>Graph nodes</h3>
                  <p>
                    {enteredNodes.length}/{maxGraphNodes} entered
                  </p>
                </div>
                <button
                  type="button"
                  className="quiet small"
                  disabled={running || nodes.length >= maxGraphNodes}
                  onClick={() => setNodes([...nodes, ''])}
                >
                  + Add node
                </button>
              </div>
              {nodes.map((node, index) => (
                <div className="dynamic-row" key={index}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <input
                    value={node}
                    onChange={(event) => updateNode(index, event.target.value)}
                    placeholder="Learning outcome / graph node"
                    disabled={running}
                  />
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => removeNode(index)}
                    disabled={running || nodes.length === 1}
                    aria-label={`Remove node ${index + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <div className="dynamic-section">
              <div className="dynamic-heading">
                <div>
                  <h3>Prerequisite relations</h3>
                  <p>Optional directed edges</p>
                </div>
                <button
                  type="button"
                  className="quiet small"
                  disabled={running || enteredNodes.length < 2}
                  onClick={() =>
                    setRelations([
                      ...relations,
                      {
                        from: enteredNodes[0] ?? '',
                        to: enteredNodes[1] ?? '',
                      },
                    ])
                  }
                >
                  + Add relation
                </button>
              </div>
              {relations.length === 0 ? (
                <div className="inline-empty">No relations defined.</div>
              ) : (
                relations.map((relation, index) => (
                  <div className="relation-row" key={index}>
                    <select
                      value={relation.from}
                      disabled={running}
                      onChange={(event) =>
                        setRelations(
                          relations.map((current, relationIndex) =>
                            relationIndex === index
                              ? { ...current, from: event.target.value }
                              : current,
                          ),
                        )
                      }
                    >
                      {enteredNodes.map((node) => (
                        <option key={node}>{node}</option>
                      ))}
                    </select>
                    <span>precedes →</span>
                    <select
                      value={relation.to}
                      disabled={running}
                      onChange={(event) =>
                        setRelations(
                          relations.map((current, relationIndex) =>
                            relationIndex === index
                              ? { ...current, to: event.target.value }
                              : current,
                          ),
                        )
                      }
                    >
                      {enteredNodes.map((node) => (
                        <option key={node}>{node}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="icon-button"
                      disabled={running}
                      onClick={() =>
                        setRelations(
                          relations.filter(
                            (_, relationIndex) => relationIndex !== index,
                          ),
                        )
                      }
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
            <div className="simulation-actions">
              <button className="primary" disabled={running}>
                {runState === 'idle' ? 'Run experiment' : 'Run again'}
              </button>
              <button type="button" className="quiet" onClick={cancel} disabled={!running}>
                Cancel
              </button>
              <button type="button" className="quiet" onClick={reset}>
                Reset
              </button>
            </div>
          </form>

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
              {view?.status === 'active' && (
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
        </section>

        <aside className="terminal panel">
          <div className="terminal-header">
            <div>
              <span className="terminal-lights">● ● ●</span>
              <strong>Experiment terminal</strong>
            </div>
            <span>{events.length} events</span>
          </div>
          <div className="terminal-body" ref={terminalRef}>
            {events.length === 0 ? (
              <p className="terminal-empty">
                Diagnostics will appear here after an experiment begins.
              </p>
            ) : (
              events.map((event) => (
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
