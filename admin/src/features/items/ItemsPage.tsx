import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Dialog } from '../../shared/ui/Dialog'
import { StatusChip, type StatusTone } from '../../shared/ui/Alert'
import { CloseIcon } from '../../shared/ui/icons'
import { TableContainer } from '../../shared/ui/TableContainer'
import {
  api,
  errorMessage,
  type AdminItem,
  type CourseChoice,
  type EditableItem,
  type ItemPage,
  type ItemStatus,
  type SaveMode,
} from '../../shared/api/adminApi'

const PAGE_SIZE = 20
const statuses: ItemStatus[] = ['draft', 'usable', 'review', 'archived']
const statusLabels: Record<ItemStatus, string> = {
  draft: 'Mustand',
  usable: 'Kasutatav',
  review: 'Ülevaatamisel',
  archived: 'Arhiveeritud',
}

const statusTones: Record<ItemStatus, StatusTone> = {
  draft: 'neutral',
  usable: 'success',
  review: 'warning',
  archived: 'error',
}

type Props = {
  courses: CourseChoice[]
}

export function ItemsPage({ courses }: Props) {
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
      { signal: controller.signal },
    )
      .then(setPage)
      .catch((caught: unknown) => setError(errorMessage(caught)))
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [offset, searchedCourse])

  function search(event: FormEvent) {
    event.preventDefault()
    const course = courseInput.trim()
    if (!course) {
      setError('Sisesta täpne kursuse kood.')
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
      {},
    )
    setPage(next)
  }

  function startEditing(item: AdminItem) {
    setEditing(item)
    setDraft(itemToEditable(item))
    setMode('create_copy')
    setError('')
  }

  function closeEditor() {
    setEditing(null)
    setDraft(null)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editing || !draft) return
    if (
      !draft.instruction.trim() ||
      !draft.prompt.trim() ||
      !draft.answer_key.trim()
    ) {
      setError('Juhis, küsimus ja õige vastus on kohustuslikud.')
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
      setError('Mõõteparameetrid peavad olema lõplikud; BLIM-i tõenäosused on vahemikus 0–1.')
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
          ? 'Muutusid olek või mõõteparameetrid. Selle ID uuendamine võib mõjutada aktiivseid testiseansse. Jätkata?'
          : 'Kas uuendada seda küsimust sama ID-ga? Sisu muutmine võib mõjutada aktiivseid testiseansse.',
      )
      if (!accepted) return
    }
    setSaving(true)
    setError('')
    try {
      const saved = await api<AdminItem>(
        `/api/v1/admin/items/${editing.yp_id}`,
        {
          method: 'PUT',
          json: { ...draft, mode },
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
          <p className="eyebrow">Küsimuste haldus</p>
          <h1>Küsimuste kontroll ja muutmine</h1>
        </div>
      </div>

      <form className="search-bar panel" onSubmit={search}>
        <label>
          <span>Täpne kursuse kood</span>
          <input
            list="audit-course-codes"
            value={courseInput}
            onChange={(event) => setCourseInput(event.target.value)}
            placeholder="Sisesta kursuse kood"
          />
          <datalist id="audit-course-codes">
            {courses.map((course) => (
              <option key={course.value} value={course.value}>
                {course.title}
              </option>
            ))}
          </datalist>
        </label>
        <button className="primary">Otsi küsimusi</button>
      </form>
      {error && <div className="notice error">{error}</div>}
      {newItemId !== null && (
        <div className="notice success">
          Uus versioon loodi ID-ga <strong>{newItemId}</strong>. Algne küsimus jäi muutmata.
        </div>
      )}

      <section className="panel audit-table-panel">
        <div className="section-heading">
          <div>
            <h2>{searchedCourse || 'Küsimuste kogu'}</h2>
          </div>
          <span className="count">{page?.total ?? 0} küsimust</span>
        </div>
        {loading ? (
          <div className="empty">Laadin küsimusi…</div>
        ) : !page || page.items.length === 0 ? (
          <div className="empty">
            {searchedCourse
              ? 'Selle kursuse koodiga küsimusi ei leitud.'
              : 'Kontrolli alustamiseks otsi kursuse koodi.'}
          </div>
        ) : (
          <TableContainer className="table-scroll">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Teadmiste sõlm</th>
                  <th>Kognitiivne tase</th>
                  <th>Küsimus</th>
                  <th>Olek</th>
                  <th>Kasutuskorrad</th>
                  <th>Viimati kasutatud</th>
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
          </TableContainer>
        )}
        {page && page.total > PAGE_SIZE && (
          <div className="pagination">
            <button
              className="quiet"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Eelmine
            </button>
            <span>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} /{' '}
              {page.total}
            </span>
            <button
              className="quiet"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Järgmine
            </button>
          </div>
        )}
      </section>

      {editing && draft && (
        <Dialog open title="Kontrollitud muudatus" onClose={closeEditor}>
          <form className="editor" onSubmit={save}>
            <div className="editor-header">
              <div>
                <p className="eyebrow">Muudan küsimust ID-ga {editing.yp_id}</p>
                <h2>Kontrollitud muudatus</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Sulge muutmine"
                onClick={closeEditor}
              >
                <CloseIcon />
              </button>
            </div>
            <fieldset className="mode-choice">
              <legend>Salvestusviis</legend>
              <label className={mode === 'create_copy' ? 'selected' : ''}>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === 'create_copy'}
                  onChange={() => setMode('create_copy')}
                />
                <span>
                  <strong>Loo muudetud koopia</strong>
                  <small>
                    Säilita kursuse ja teadmiste sõlme andmed; lähtesta kasutusandmed.
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
                  <strong>Uuenda praegust küsimust</strong>
                  <small>
                    Säilita ID ja kasutusandmed. Aktiivsed seansid võivad muutuda.
                  </small>
                </span>
              </label>
            </fieldset>
            <div className="editor-grid">
              <label>
                <span>Juhis</span>
                <input
                  value={draft.instruction}
                  onChange={(event) =>
                    setDraft({ ...draft, instruction: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Olek</span>
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
                    <option key={status} value={status}>{statusLabels[status]}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                <span>Küsimus</span>
                <textarea
                  rows={3}
                  value={draft.prompt}
                  onChange={(event) =>
                    setDraft({ ...draft, prompt: event.target.value })
                  }
                />
              </label>
              <label className="wide">
                <span>Lähteinfo · valikuline</span>
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
                  ['answer_key', 'Õige vastus'],
                  ['distractor_1', 'Segaja 1'],
                  ['distractor_2', 'Segaja 2'],
                  ['distractor_3', 'Segaja 3'],
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
                  ['beta_error', 'BLIM-i β-viga'],
                  ['guess_probability', 'BLIM-i äraarvamine'],
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
                ? 'Kursuse, sõlme, vanema, kognitiivse taseme ja muud andmed kopeeritakse. Kasutusandmed lähtestatakse.'
                : 'Kõik muud andmed ja olemasolevad kasutusandmed jäävad selle ID-ga seotuks.'}
            </div>
            <div className="editor-actions">
              <button
                type="button"
                className="quiet"
                onClick={closeEditor}
              >
                Tühista
              </button>
              <button className="primary" disabled={saving}>
                {saving
                  ? 'Salvestan…'
                  : mode === 'create_copy'
                    ? 'Loo muudetud koopia'
                    : 'Uuenda küsimust'}
              </button>
            </div>
          </form>
        </Dialog>
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
          <StatusChip tone={statusTones[item.status]}>{statusLabels[item.status]}</StatusChip>
        </td>
        <td>{item.usage_count}</td>
        <td>{item.last_used_at ? new Date(item.last_used_at).toLocaleString() : '—'}</td>
        <td>
          <button className="quiet small" type="button" onClick={onToggle}>
            {expanded ? 'Sulge' : 'Vaata'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="details-row">
          <td colSpan={8}>
            <div className="item-details">
              <Detail label="Juhis" value={item.instruction} />
              <Detail label="Lähteinfo" value={item.stimulus ?? '—'} />
              <Detail label="Õige vastus" value={item.answer_key} />
              <Detail
                label="Segajad"
                value={[
                  item.distractor_1,
                  item.distractor_2,
                  item.distractor_3,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              />
              <Detail label="Ülemine sõlm" value={item.parent_graph_node ?? '—'} />
              <Detail label="Punktid" value={String(item.score)} />
              <Detail
                label="IRT / BLIM"
                value={`a ${item.irt_a} · b ${item.irt_b} · β ${item.beta_error} · g ${item.guess_probability}`}
              />
              <button className="secondary" type="button" onClick={onEdit}>
                Ava muutmine
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
