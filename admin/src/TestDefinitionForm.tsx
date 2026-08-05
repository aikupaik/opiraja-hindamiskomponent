import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import type {
  CourseChoice,
  CreateTestPayload,
  TestRelation,
} from './api'

type Props = {
  courses: CourseChoice[]
  maxGraphNodes: number
  disabled: boolean
  submitLabel: string
  status?: ReactNode
  actions?: ReactNode
  onSubmit: (payload: CreateTestPayload) => void | Promise<void>
}

export function TestDefinitionForm({
  courses,
  maxGraphNodes,
  disabled,
  submitLabel,
  status,
  actions,
  onSubmit,
}: Props) {
  const [userId, setUserId] = useState('admin-simulation-user')
  const [learningPathId, setLearningPathId] = useState('manual-experiment')
  const [course, setCourse] = useState(courses[0]?.value ?? '')
  const [goal, setGoal] = useState<'real_test' | 'trial_run'>('trial_run')
  const [nodes, setNodes] = useState<string[]>([''])
  const [relations, setRelations] = useState<TestRelation[]>([])
  const [validationError, setValidationError] = useState('')

  useEffect(() => {
    if (!course && courses[0]) setCourse(courses[0].value)
  }, [course, courses])

  const enteredNodes = nodes.map((node) => node.trim()).filter(Boolean)

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

  function submit(event: FormEvent) {
    event.preventDefault()
    setValidationError('')
    const normalizedNodes = nodes.map((node) => node.trim()).filter(Boolean)
    if (!userId.trim() || !learningPathId.trim() || !course) {
      setValidationError('User, learning path, and course are required.')
      return
    }
    if (
      normalizedNodes.length === 0 ||
      normalizedNodes.length > maxGraphNodes ||
      new Set(normalizedNodes).size !== normalizedNodes.length
    ) {
      setValidationError(
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
      setValidationError('Every relation needs two different entered nodes.')
      return
    }

    void onSubmit({
      user_id: userId.trim(),
      learning_path_id: learningPathId.trim(),
      course,
      goal,
      method: 'kst',
      cognitive_level: 'mõistab',
      nodes: normalizedNodes,
      relations,
    })
  }

  return (
    <form className="panel simulation-form" onSubmit={submit}>
      <div className="section-heading">
        <div>
          <h2>Test definition</h2>
          <p>Method kst · cognitive level mõistab</p>
        </div>
        {status}
      </div>
      {validationError && <div className="notice error">{validationError}</div>}
      <div className="field-row">
        <label>
          <span>User ID</span>
          <input
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            disabled={disabled}
          />
        </label>
        <label>
          <span>Learning path ID</span>
          <input
            value={learningPathId}
            onChange={(event) => setLearningPathId(event.target.value)}
            disabled={disabled}
          />
        </label>
      </div>
      <div className="field-row">
        <label>
          <span>Course</span>
          <select
            value={course}
            onChange={(event) => setCourse(event.target.value)}
            disabled={disabled}
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
            disabled={disabled}
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
            <p>{enteredNodes.length}/{maxGraphNodes} entered</p>
          </div>
          <button
            type="button"
            className="quiet small"
            disabled={disabled || nodes.length >= maxGraphNodes}
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
              disabled={disabled}
            />
            <button
              type="button"
              className="icon-button"
              onClick={() => removeNode(index)}
              disabled={disabled || nodes.length === 1}
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
            <p>The parent prerequisite must be learned before the child.</p>
          </div>
          <button
            type="button"
            className="quiet small"
            disabled={disabled || enteredNodes.length < 2}
            onClick={() => setRelations([...relations, { from: '', to: '' }])}
          >
            + Add relation
          </button>
        </div>
        {relations.length === 0 ? (
          <div className="inline-empty">No relations defined.</div>
        ) : (
          relations.map((relation, index) => (
            <div className="relation-row" key={index}>
              <label>
                <span>Prerequisite node (parent)</span>
                <select
                  value={relation.from}
                  disabled={disabled}
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
                  <option value="">Select prerequisite</option>
                  {enteredNodes.map((node) => <option key={node}>{node}</option>)}
                </select>
              </label>
              <span>precedes →</span>
              <label>
                <span>Dependent node (child)</span>
                <select
                  value={relation.to}
                  disabled={disabled}
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
                  <option value="">Select dependent node</option>
                  {enteredNodes.map((node) => <option key={node}>{node}</option>)}
                </select>
              </label>
              <button
                type="button"
                className="icon-button"
                disabled={disabled}
                onClick={() =>
                  setRelations(
                    relations.filter((_, relationIndex) => relationIndex !== index),
                  )
                }
                aria-label={`Remove relation ${index + 1}`}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
      <div className="simulation-actions">
        <button className="primary" disabled={disabled}>{submitLabel}</button>
        {actions}
      </div>
    </form>
  )
}
