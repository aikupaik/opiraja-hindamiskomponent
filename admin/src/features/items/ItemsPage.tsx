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
  const [mode, setMode] = useState<SaveMode | null>(null)
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
    setMode(null)
    setError('')
  }

  function closeEditor() {
    if (saving) return
    if (
      editing &&
      draft &&
      itemHasChanged(editing, draft) &&
      !window.confirm('Kas loobuda muudatustest? Salvestamata muudatused lähevad kaotsi.')
    ) {
      return
    }
    setEditing(null)
    setDraft(null)
    setMode(null)
    setError('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editing || !draft) return
    if (!mode) {
      setError('Vali, kuidas soovid muudatuse salvestada.')
      return
    }
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
          ? 'Olek või hindamisparameetrid muutusid. Olemasoleva ülesande muutmine võib mõjutada aktiivseid testiseansse. Kas jätkata?'
          : 'Kas soovid olemasolevat ülesannet muuta? Sisu muutmine võib mõjutada aktiivseid testiseansse.',
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
          <p className="eyebrow">Ülesannete haldus</p>
          <h1>Ülesannete vaatamine ja muutmine</h1>
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
        <button className="primary">Otsi ülesandeid</button>
      </form>
      {error && !editing && <div className="notice error">{error}</div>}
      {newItemId !== null && (
        <div className="notice success">
          Uus versioon loodi ID-ga <strong>{newItemId}</strong>. Algne ülesanne jäi muutmata.
        </div>
      )}

      <section className="panel audit-table-panel">
        <div className="section-heading">
          <div>
            <h2>{searchedCourse || 'Ülesannete kogu'}</h2>
          </div>
          <span className="count">{page?.total ?? 0} ülesannet</span>
        </div>
        {loading ? (
          <div className="empty">Laadin ülesandeid…</div>
        ) : !page || page.items.length === 0 ? (
          <div className="empty">
            {searchedCourse
              ? 'Selle kursuse koodiga ülesandeid ei leitud.'
              : 'Ülesannete vaatamiseks otsi kursuse koodi.'}
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
        <Dialog open title="Muuda ülesannet" onClose={closeEditor}>
          <form className="editor" onSubmit={save}>
            <div className="editor-header">
              <div>
                <p className="eyebrow">Ülesanne ID {editing.yp_id}</p>
                <h2>Muuda ülesannet</h2>
                <p className="editor-intro">
                  Tee vajalikud parandused.
                </p>
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
            {error && <div className="notice error" role="alert">{error}</div>}
            <div className="editor-grid">
              <label className="wide">
                <span>Juhis</span>
                <input
                  value={draft.instruction}
                  onChange={(event) =>
                    setDraft({ ...draft, instruction: event.target.value })
                  }
                />
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
            </div>
            <details className="editor-advanced">
              <summary>Täiendavad seaded</summary>
              <div className="editor-grid editor-settings-grid">
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
            </details>
            <fieldset className="mode-choice">
              <legend>Kuidas soovid muudatuse salvestada?</legend>
              <label className={mode === 'create_copy' ? 'selected' : ''}>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === 'create_copy'}
                  onChange={() => setMode('create_copy')}
                />
                <span>
                  <strong>Loo uus ülesanne</strong>
                  <small>
                    Algne ülesanne jääb alles. Uuel ülesandel on uus ID ja kasutusajalugu algab nullist.
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
                  <strong>Paranda olemasolevat ülesannet</strong>
                  <small>
                    ID ja kasutusajalugu säilivad.
                  </small>
                </span>
              </label>
            </fieldset>
            <div className="editor-actions">
              <button
                type="button"
                className="quiet"
                onClick={closeEditor}
              >
                Loobu muudatustest
              </button>
              <button className="primary" disabled={saving || !mode}>
                {saving
                  ? 'Salvestan…'
                  : mode === 'create_copy'
                    ? 'Loo uus ülesanne'
                    : mode === 'update_existing'
                      ? 'Paranda olemasolevat ülesannet'
                      : 'Vali salvestusviis'}
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
              <section className="item-preview" aria-labelledby={`item-${item.yp_id}-title`}>
                <h3 id={`item-${item.yp_id}-title`}>Ülesanne</h3>
                <p className="item-instruction">{item.instruction}</p>
                {item.stimulus && (
                  <div className="item-stimulus">
                    <span>Lähteinfo</span>
                    <p>{item.stimulus}</p>
                  </div>
                )}
                <p className="item-prompt">{item.prompt}</p>
                <div className="item-answer-options">
                  <div>
                    <span>Õige vastus</span>
                    <p>{item.answer_key}</p>
                  </div>
                  <div>
                    <span>Segajad</span>
                    <ul aria-label="Segajad" className="distractor-list">
                      {[item.distractor_1, item.distractor_2, item.distractor_3]
                        .filter((distractor): distractor is string => Boolean(distractor))
                        .map((distractor, index) => (
                          <li key={`${index}-${distractor}`}>{distractor}</li>
                        ))}
                    </ul>
                  </div>
                </div>
              </section>
              <div className="item-metadata">
                <Detail label="Ülemine sõlm" value={item.parent_graph_node ?? '—'} />
                <Detail label="Punktid" value={String(item.score)} />
                <Detail
                  label="IRT / BLIM"
                  value={`a ${item.irt_a} · b ${item.irt_b} · β ${item.beta_error} · g ${item.guess_probability}`}
                />
                <button className="secondary" type="button" onClick={onEdit}>
                  Muuda ülesannet
                </button>
              </div>
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

function itemHasChanged(item: AdminItem, draft: EditableItem) {
  return (
    item.instruction !== draft.instruction ||
    item.prompt !== draft.prompt ||
    item.stimulus !== draft.stimulus ||
    item.answer_key !== draft.answer_key ||
    item.distractor_1 !== draft.distractor_1 ||
    item.distractor_2 !== draft.distractor_2 ||
    item.distractor_3 !== draft.distractor_3 ||
    item.status !== draft.status ||
    item.irt_a !== draft.irt_a ||
    item.irt_b !== draft.irt_b ||
    item.beta_error !== draft.beta_error ||
    item.guess_probability !== draft.guess_probability
  )
}
