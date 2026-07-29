import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  errorMessage,
  jsonBody,
  type CourseChoice,
  type SourceMaterial,
  type YgRule,
} from './api'

type Props = {
  accessKey: string
  courses: CourseChoice[]
  refreshCourses: () => Promise<void>
}

export function MaterialsPage({
  accessKey,
  courses,
  refreshCourses,
}: Props) {
  const [selectedCourse, setSelectedCourse] = useState(courses[0]?.value ?? '')
  const [materials, setMaterials] = useState<SourceMaterial[]>([])
  const [rules, setRules] = useState<YgRule[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<Record<number, SourceMaterial>>({})
  const [savedPreview, setSavedPreview] = useState<SourceMaterial | null>(null)
  const [courseCode, setCourseCode] = useState(courses[0]?.value ?? '')
  const [courseTitle, setCourseTitle] = useState(courses[0]?.title ?? '')
  const [sourceUrl, setSourceUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [savingMaterial, setSavingMaterial] = useState(false)
  const [ruleCourse, setRuleCourse] = useState(courses[0]?.value ?? '')
  const [ruleDescription, setRuleDescription] = useState('')
  const [ruleExample, setRuleExample] = useState('{}')
  const [savingRule, setSavingRule] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!selectedCourse && courses[0]) setSelectedCourse(courses[0].value)
    if (!courseCode && courses[0]) {
      setCourseCode(courses[0].value)
      setCourseTitle(courses[0].title)
    }
    if (!ruleCourse && courses[0]) setRuleCourse(courses[0].value)
  }, [courses, courseCode, ruleCourse, selectedCourse])

  useEffect(() => {
    if (!selectedCourse) {
      setMaterials([])
      setRules([])
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError('')
    Promise.all([
      api<SourceMaterial[]>(
        `/api/v1/admin/source-materials?course=${encodeURIComponent(selectedCourse)}`,
        { key: accessKey, signal: controller.signal },
      ),
      api<YgRule[]>(
        `/api/v1/admin/yg-rules?course=${encodeURIComponent(selectedCourse)}`,
        { key: accessKey, signal: controller.signal },
      ),
    ])
      .then(([nextMaterials, nextRules]) => {
        setMaterials(nextMaterials)
        setRules(nextRules)
      })
      .catch((caught: unknown) => setError(errorMessage(caught)))
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [accessKey, selectedCourse])

  async function refreshLists(course: string) {
    const [nextMaterials, nextRules] = await Promise.all([
      api<SourceMaterial[]>(
        `/api/v1/admin/source-materials?course=${encodeURIComponent(course)}`,
        { key: accessKey },
      ),
      api<YgRule[]>(
        `/api/v1/admin/yg-rules?course=${encodeURIComponent(course)}`,
        { key: accessKey },
      ),
    ])
    setMaterials(nextMaterials)
    setRules(nextRules)
  }

  async function submitMaterial(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!courseCode.trim() || !courseTitle.trim()) {
      setError('Course code and course title are required.')
      return
    }
    if (!sourceUrl.trim() && !file) {
      setError('Choose a file or enter a public source URL.')
      return
    }
    const form = new FormData()
    form.set('course', courseCode.trim())
    form.set('title', courseTitle.trim())
    if (sourceUrl.trim()) form.set('source_url', sourceUrl.trim())
    if (file) form.set('file', file)
    setSavingMaterial(true)
    try {
      const saved = await api<SourceMaterial>('/api/v1/admin/source-materials', {
        key: accessKey,
        method: 'POST',
        body: form,
      })
      setSavedPreview(saved)
      setSelectedCourse(saved.course)
      setSourceUrl('')
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      await Promise.all([refreshCourses(), refreshLists(saved.course)])
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSavingMaterial(false)
    }
  }

  async function submitRule(event: FormEvent) {
    event.preventDefault()
    setError('')
    let example: unknown
    try {
      example = JSON.parse(ruleExample)
      if (example === null) throw new Error()
    } catch {
      setError('Rule example must be valid, non-null JSON.')
      return
    }
    if (!ruleCourse.trim() || !ruleDescription.trim()) {
      setError('Rule course and description are required.')
      return
    }
    setSavingRule(true)
    try {
      await api<YgRule>('/api/v1/admin/yg-rules', {
        key: accessKey,
        method: 'POST',
        body: jsonBody({
          course: ruleCourse.trim(),
          description: ruleDescription.trim(),
          example,
        }),
      })
      setRuleDescription('')
      setRuleExample('{}')
      setSelectedCourse(ruleCourse.trim())
      await refreshLists(ruleCourse.trim())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSavingRule(false)
    }
  }

  async function toggleMaterial(material: SourceMaterial) {
    if (expanded[material.id]) {
      setExpanded((current) => {
        const next = { ...current }
        delete next[material.id]
        return next
      })
      return
    }
    try {
      const complete = await api<SourceMaterial>(
        `/api/v1/admin/source-materials/${material.id}`,
        { key: accessKey },
      )
      setExpanded((current) => ({ ...current, [material.id]: complete }))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  function chooseKnownCourse(value: string) {
    setCourseCode(value)
    const course = courses.find((choice) => choice.value === value)
    if (course) setCourseTitle(course.title)
  }

  return (
    <main className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Knowledge source control</p>
          <h1>Course materials</h1>
          <p>Curate source text and future-facing YG authoring rules.</p>
        </div>
        <label className="compact-field">
          <span>Viewing course</span>
          <select
            value={selectedCourse}
            onChange={(event) => setSelectedCourse(event.target.value)}
          >
            <option value="">Select a course</option>
            {courses.map((course) => (
              <option key={course.value} value={course.value}>
                {course.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="notice error">{error}</div>}
      <section className="form-grid">
        <form className="panel" onSubmit={submitMaterial}>
          <div className="panel-title">
            <span className="step">01</span>
            <div>
              <h2>Add source material</h2>
              <p>Upload takes precedence when a URL is also supplied.</p>
            </div>
          </div>
          <div className="field-row">
            <label>
              <span>Course code</span>
              <input
                list="course-codes"
                value={courseCode}
                onChange={(event) => chooseKnownCourse(event.target.value)}
                placeholder="e.g. FÜS101"
              />
              <datalist id="course-codes">
                {courses.map((course) => (
                  <option key={course.value} value={course.value}>
                    {course.title}
                  </option>
                ))}
              </datalist>
            </label>
            <label>
              <span>Course title</span>
              <input
                value={courseTitle}
                onChange={(event) => setCourseTitle(event.target.value)}
                placeholder="Human-readable course title"
              />
            </label>
          </div>
          <label>
            <span>Public source URL · optional</span>
            <input
              type="url"
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://…"
            />
          </label>
          <label className="file-drop">
            <span>PDF, TXT, or Markdown · optional</span>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <strong>{file ? file.name : 'Choose a source file'}</strong>
            <small>Binaries are parsed, never stored.</small>
          </label>
          <button className="primary" disabled={savingMaterial}>
            {savingMaterial ? 'Extracting…' : 'Extract and save'}
          </button>
          {savedPreview && (
            <div className="saved-preview">
              <strong>Saved #{savedPreview.id}</strong>
              <p>{savedPreview.content_preview}</p>
            </div>
          )}
        </form>

        <form className="panel" onSubmit={submitRule}>
          <div className="panel-title">
            <span className="step">02</span>
            <div>
              <h2>Add YG rule</h2>
              <p>Stored for inspection; execution is outside this phase.</p>
            </div>
          </div>
          <label>
            <span>Course</span>
            <input
              list="rule-course-codes"
              value={ruleCourse}
              onChange={(event) => setRuleCourse(event.target.value)}
              placeholder="Course code"
            />
            <datalist id="rule-course-codes">
              {courses.map((course) => (
                <option key={course.value} value={course.value} />
              ))}
            </datalist>
          </label>
          <label>
            <span>Rule description</span>
            <textarea
              value={ruleDescription}
              onChange={(event) => setRuleDescription(event.target.value)}
              rows={5}
              placeholder="Describe the authoring constraint…"
            />
          </label>
          <label>
            <span>Valid JSON example</span>
            <textarea
              className="mono"
              value={ruleExample}
              onChange={(event) => setRuleExample(event.target.value)}
              rows={6}
            />
          </label>
          <button className="secondary" disabled={savingRule}>
            {savingRule ? 'Saving…' : 'Save rule'}
          </button>
        </form>
      </section>

      <section className="panel collection">
        <div className="section-heading">
          <div>
            <h2>Source inventory</h2>
            <p>{selectedCourse || 'No course selected'}</p>
          </div>
          <span className="count">{materials.length} sources</span>
        </div>
        {loading ? (
          <div className="empty">Loading course data…</div>
        ) : materials.length === 0 ? (
          <div className="empty">No source materials for this course.</div>
        ) : (
          <div className="material-list">
            {materials.map((material) => (
              <article key={material.id} className="material">
                <button
                  className="material-summary"
                  type="button"
                  onClick={() => void toggleMaterial(material)}
                >
                  <span className="material-id">#{material.id}</span>
                  <span>
                    <strong>{material.title}</strong>
                    <small>{material.source_url ?? 'No provenance'}</small>
                  </span>
                  <span className="material-date">
                    {formatDate(material.added_at)}
                  </span>
                  <span>{expanded[material.id] ? '−' : '+'}</span>
                </button>
                <p>{material.content_preview}</p>
                {expanded[material.id] && (
                  <pre className="full-text">
                    {expanded[material.id].content}
                  </pre>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel collection">
        <div className="section-heading">
          <div>
            <h2>YG rules</h2>
            <p>Visible configuration only</p>
          </div>
          <span className="count">{rules.length} rules</span>
        </div>
        {rules.length === 0 ? (
          <div className="empty">No rules for this course.</div>
        ) : (
          <div className="rule-list">
            {rules.map((rule) => (
              <article key={rule.id}>
                <span>#{rule.id}</span>
                <p>{rule.description}</p>
                <pre>{JSON.stringify(rule.example, null, 2)}</pre>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—'
}
