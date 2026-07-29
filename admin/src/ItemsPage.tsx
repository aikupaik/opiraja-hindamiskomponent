import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  errorMessage,
  jsonBody,
  type AdminItem,
  type CourseChoice,
  type EditableItem,
  type ItemPage,
  type ItemStatus,
  type SaveMode,
} from './api'

const PAGE_SIZE = 20
const statuses: ItemStatus[] = ['draft', 'usable', 'review', 'archived']

type Props = {
  accessKey: string
  courses: CourseChoice[]
}

export function ItemsPage({ accessKey, courses }: Props) {
  const [courseInput, setCourseInput] = useState('')
  const [searchedCourse, setSearchedCourse] = useState('')
  const [page, setPage] = useState<ItemPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editing, setEditing] = useState<AdminItem | null>(null)
  const [draft, setDraft] = useState<EditableItem | null>(null)
  const [mode, setMode] = useState<SaveMode>('create_copy')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [newItemId, setNewItemId] = useState<number | null>(null)

  useEffect(() => {
    if (!searchedCourse) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    api<ItemPage>(
      `/api/v1/admin/items?course=${encodeURIComponent(searchedCourse)}&limit=${PAGE_SIZE}&offset=${offset}`,
      { key: accessKey, signal: controller.signal },
    )
      .then(setPage)
      .catch((caught: unknown) => setError(errorMessage(caught)))
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [accessKey, offset, searchedCourse])

  function search(event: FormEvent) {
    event.preventDefault()
    const course = courseInput.trim()
    if (!course) {
      setError('Enter an exact course code.')
      return
    }
    setOffset(0)
    setSearchedCourse(course)
    setNewItemId(null)
  }

  async function refresh() {
    if (!searchedCourse) return
    const next = await api<ItemPage>(
      `/api/v1/admin/items?course=${encodeURIComponent(searchedCourse)}&limit=${PAGE_SIZE}&offset=${offset}`,
      { key: accessKey },
    )
    setPage(next)
  }

  function startEditing(item: AdminItem) {
    setEditing(item)
    setDraft(itemToEditable(item))
    setMode('create_copy')
    setError('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editing || !draft) return
    if (
      !draft.instruction.trim() ||
      !draft.prompt.trim() ||
      !draft.answer_key.trim()
    ) {
      setError('Instruction, question stem, and answer key are required.')
      return
    }
    if (
      !Number.isFinite(draft.irt_a) ||
      !Number.isFinite(draft.irt_b) ||
      !Number.isFinite(draft.beta_error) ||
      !Number.isFinite(draft.guess_probability) ||
      draft.beta_error < 0 ||
      draft.beta_error > 1 ||
      draft.guess_probability < 0 ||
      draft.guess_probability > 1
    ) {
      setError('Measurement values must be finite; BLIM probabilities use 0–1.')
      return
    }
    if (mode === 'update_existing') {
      const stronger =
        editing.status !== draft.status ||
        editing.irt_a !== draft.irt_a ||
        editing.irt_b !== draft.irt_b ||
        editing.beta_error !== draft.beta_error ||
        editing.guess_probability !== draft.guess_probability
      const accepted = window.confirm(
        stronger
          ? 'High-impact change: status or measurement parameters changed. Updating this ID may affect active assessment sessions. Continue?'
          : 'Update this item ID in place? Content changes may affect active assessment sessions.',
      )
      if (!accepted) return
    }
    setSaving(true)
    setError('')
    try {
      const saved = await api<AdminItem>(
        `/api/v1/admin/items/${editing.yp_id}`,
        {
          key: accessKey,
          method: 'PUT',
          body: jsonBody({ ...draft, mode }),
        },
      )
      setNewItemId(mode === 'create_copy' ? saved.yp_id : null)
      setEditing(null)
      setDraft(null)
      await refresh()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Item-bank governance</p>
          <h1>Audit & revision</h1>
          <p>Inspect exact-course inventory without changing player semantics.</p>
        </div>
      </div>

      <form className="search-bar panel" onSubmit={search}>
        <label>
          <span>Exact course code</span>
          <input
            list="audit-course-codes"
            value={courseInput}
            onChange={(event) => setCourseInput(event.target.value)}
            placeholder="Enter a course code"
          />
          <datalist id="audit-course-codes">
            {courses.map((course) => (
              <option key={course.value} value={course.value}>
                {course.title}
              </option>
            ))}
          </datalist>
        </label>
        <button className="primary">Search item bank</button>
      </form>
      {error && <div className="notice error">{error}</div>}
      {newItemId !== null && (
        <div className="notice success">
          Revised copy created as <strong>yp_id {newItemId}</strong>. The source
          item remains unchanged.
        </div>
      )}

      <section className="panel audit-table-panel">
        <div className="section-heading">
          <div>
            <h2>{searchedCourse || 'Item inventory'}</h2>
            <p>Ordered by stable item ID</p>
          </div>
          <span className="count">{page?.total ?? 0} items</span>
        </div>
        {loading ? (
          <div className="empty">Loading items…</div>
        ) : !page || page.items.length === 0 ? (
          <div className="empty">
            {searchedCourse
              ? 'No items found for this exact course code.'
              : 'Search for a course to begin the audit.'}
          </div>
        ) : (
          <div className="table-scroll">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Node</th>
                  <th>Cognitive</th>
                  <th>Question stem</th>
                  <th>Status</th>
                  <th>Uses</th>
                  <th>Last used</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {page.items.map((item) => (
                  <ItemRows
                    key={item.yp_id}
                    item={item}
                    expanded={expandedId === item.yp_id}
                    highlighted={newItemId === item.yp_id}
                    onToggle={() =>
                      setExpandedId((current) =>
                        current === item.yp_id ? null : item.yp_id,
                      )
                    }
                    onEdit={() => startEditing(item)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page && page.total > PAGE_SIZE && (
          <div className="pagination">
            <button
              className="quiet"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <span>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of{' '}
              {page.total}
            </span>
            <button
              className="quiet"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        )}
      </section>

      {editing && draft && (
        <div className="editor-backdrop" role="presentation">
          <form className="editor" onSubmit={save}>
            <div className="editor-header">
              <div>
                <p className="eyebrow">Editing source yp_id {editing.yp_id}</p>
                <h2>Controlled revision</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close editor"
                onClick={() => setEditing(null)}
              >
                ×
              </button>
            </div>
            <fieldset className="mode-choice">
              <legend>Save mode</legend>
              <label className={mode === 'create_copy' ? 'selected' : ''}>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === 'create_copy'}
                  onChange={() => setMode('create_copy')}
                />
                <span>
                  <strong>Create revised copy</strong>
                  <small>
                    Preserve graph/course metadata; reset use count and last use.
                  </small>
                </span>
              </label>
              <label className={mode === 'update_existing' ? 'selected' : ''}>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === 'update_existing'}
                  onChange={() => setMode('update_existing')}
                />
                <span>
                  <strong>Update current item</strong>
                  <small>
                    Keep this ID and telemetry. Active sessions may be affected.
                  </small>
                </span>
              </label>
            </fieldset>
            <div className="editor-grid">
              <label>
                <span>Instruction</span>
                <input
                  value={draft.instruction}
                  onChange={(event) =>
                    setDraft({ ...draft, instruction: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Status</span>
                <select
                  value={draft.status}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      status: event.target.value as ItemStatus,
                    })
                  }
                >
                  {statuses.map((status) => (
                    <option key={status}>{status}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                <span>Question stem</span>
                <textarea
                  rows={3}
                  value={draft.prompt}
                  onChange={(event) =>
                    setDraft({ ...draft, prompt: event.target.value })
                  }
                />
              </label>
              <label className="wide">
                <span>Stimulus · optional</span>
                <textarea
                  rows={3}
                  value={draft.stimulus ?? ''}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      stimulus: event.target.value || null,
                    })
                  }
                />
              </label>
              {(
                [
                  ['answer_key', 'Answer key'],
                  ['distractor_1', 'Distractor 1'],
                  ['distractor_2', 'Distractor 2'],
                  ['distractor_3', 'Distractor 3'],
                ] as const
              ).map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <input
                    value={draft[field] ?? ''}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        [field]: event.target.value || null,
                      })
                    }
                  />
                </label>
              ))}
              {(
                [
                  ['irt_a', 'IRT a'],
                  ['irt_b', 'IRT b'],
                  ['beta_error', 'BLIM β error'],
                  ['guess_probability', 'BLIM guess'],
                ] as const
              ).map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <input
                    type="number"
                    step="any"
                    value={draft[field]}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        [field]: event.target.valueAsNumber,
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <div className="editor-note">
              {mode === 'create_copy'
                ? 'Course, node, parent, cognitive level, score, and other metadata are copied. Usage telemetry resets to zero.'
                : 'All non-editable metadata and existing usage telemetry remain attached to this item ID.'}
            </div>
            <div className="editor-actions">
              <button
                type="button"
                className="quiet"
                onClick={() => setEditing(null)}
              >
                Cancel
              </button>
              <button className="primary" disabled={saving}>
                {saving
                  ? 'Saving…'
                  : mode === 'create_copy'
                    ? 'Create revised copy'
                    : 'Update current item'}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  )
}

function ItemRows({
  item,
  expanded,
  highlighted,
  onToggle,
  onEdit,
}: {
  item: AdminItem
  expanded: boolean
  highlighted: boolean
  onToggle: () => void
  onEdit: () => void
}) {
  return (
    <>
      <tr className={highlighted ? 'highlighted' : ''}>
        <td className="mono">{item.yp_id}</td>
        <td>{item.graph_node}</td>
        <td>{item.cognitive_level}</td>
        <td className="stem">{item.prompt}</td>
        <td>
          <span className={`status status-${item.status}`}>{item.status}</span>
        </td>
        <td>{item.usage_count}</td>
        <td>{item.last_used_at ? new Date(item.last_used_at).toLocaleString() : '—'}</td>
        <td>
          <button className="quiet small" type="button" onClick={onToggle}>
            {expanded ? 'Close' : 'Inspect'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="details-row">
          <td colSpan={8}>
            <div className="item-details">
              <Detail label="Instruction" value={item.instruction} />
              <Detail label="Stimulus" value={item.stimulus ?? '—'} />
              <Detail label="Answer key" value={item.answer_key} />
              <Detail
                label="Distractors"
                value={[
                  item.distractor_1,
                  item.distractor_2,
                  item.distractor_3,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              />
              <Detail label="Parent node" value={item.parent_graph_node ?? '—'} />
              <Detail label="Score" value={String(item.score)} />
              <Detail
                label="IRT / BLIM"
                value={`a ${item.irt_a} · b ${item.irt_b} · β ${item.beta_error} · g ${item.guess_probability}`}
              />
              <button className="secondary" type="button" onClick={onEdit}>
                Open editor
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function itemToEditable(item: AdminItem): EditableItem {
  return {
    instruction: item.instruction,
    prompt: item.prompt,
    stimulus: item.stimulus,
    answer_key: item.answer_key,
    distractor_1: item.distractor_1,
    distractor_2: item.distractor_2,
    distractor_3: item.distractor_3,
    status: item.status,
    irt_a: item.irt_a,
    irt_b: item.irt_b,
    beta_error: item.beta_error,
    guess_probability: item.guess_probability,
  }
}
