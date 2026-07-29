import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  errorMessage,
  type AdminSession,
  type CourseChoice,
} from './api'
import { ItemsPage } from './ItemsPage'
import { MaterialsPage } from './MaterialsPage'
import { SimulationPage } from './SimulationPage'
import './App.css'

const STORAGE_KEY = 'assessment-admin-access-key'
type Page = 'materials' | 'items' | 'simulation'

function App() {
  const [accessKey, setAccessKey] = useState(
    () => sessionStorage.getItem(STORAGE_KEY) ?? '',
  )
  const [session, setSession] = useState<AdminSession | null>(null)
  const [unlocking, setUnlocking] = useState(Boolean(accessKey))
  const [unlockError, setUnlockError] = useState('')
  const [page, setPage] = useState<Page>(readPage)
  const [courses, setCourses] = useState<CourseChoice[]>([])
  const [courseError, setCourseError] = useState('')

  useEffect(() => {
    const onHashChange = () => setPage(readPage())
    window.addEventListener('hashchange', onHashChange)
    if (!window.location.hash) window.location.hash = '/materials'
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY)
    if (!stored) {
      setUnlocking(false)
      return
    }
    const controller = new AbortController()
    setUnlocking(true)
    api<AdminSession>('/api/v1/admin/session', {
      key: stored,
      signal: controller.signal,
    })
      .then((validated) => {
        setAccessKey(stored)
        setSession(validated)
        setUnlockError('')
      })
      .catch((caught: unknown) => {
        sessionStorage.removeItem(STORAGE_KEY)
        setAccessKey('')
        setSession(null)
        setUnlockError(errorMessage(caught))
      })
      .finally(() => setUnlocking(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!session) {
      setCourses([])
      return
    }
    const controller = new AbortController()
    setCourseError('')
    api<CourseChoice[]>('/api/v1/admin/courses', {
      key: accessKey,
      signal: controller.signal,
    })
      .then(setCourses)
      .catch((caught: unknown) => setCourseError(errorMessage(caught)))
    return () => controller.abort()
  }, [accessKey, session])

  async function unlock(key: string) {
    setUnlocking(true)
    setUnlockError('')
    try {
      const validated = await api<AdminSession>('/api/v1/admin/session', {
        key,
      })
      sessionStorage.setItem(STORAGE_KEY, key)
      setAccessKey(key)
      setSession(validated)
    } catch (caught) {
      sessionStorage.removeItem(STORAGE_KEY)
      setUnlockError(errorMessage(caught))
      setSession(null)
    } finally {
      setUnlocking(false)
    }
  }

  function lock() {
    sessionStorage.removeItem(STORAGE_KEY)
    setAccessKey('')
    setSession(null)
    setCourses([])
    setUnlockError('')
  }

  async function refreshCourses() {
    const next = await api<CourseChoice[]>('/api/v1/admin/courses', {
      key: accessKey,
    })
    setCourses(next)
  }

  if (!session) {
    return (
      <UnlockScreen
        loading={unlocking}
        error={unlockError}
        onUnlock={unlock}
      />
    )
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="#/materials">
          <span className="brand-mark">OR</span>
          <span>
            <strong>Assessment Lab</strong>
            <small>Operator console</small>
          </span>
        </a>
        <nav aria-label="Admin sections">
          <NavLink page="materials" current={page}>
            Sources
          </NavLink>
          <NavLink page="items" current={page}>
            Item bank
          </NavLink>
          <NavLink page="simulation" current={page}>
            Simulation
          </NavLink>
        </nav>
        <div className="operator">
          <span>
            <i />
            {session.subject}
          </span>
          <button type="button" className="lock-button" onClick={lock}>
            Lock
          </button>
        </div>
      </header>
      {courseError && <div className="global-error">{courseError}</div>}
      {page === 'materials' && (
        <MaterialsPage
          accessKey={accessKey}
          courses={courses}
          refreshCourses={refreshCourses}
        />
      )}
      {page === 'items' && (
        <ItemsPage accessKey={accessKey} courses={courses} />
      )}
      {page === 'simulation' && (
        <SimulationPage
          accessKey={accessKey}
          courses={courses}
          maxGraphNodes={session.max_graph_nodes}
        />
      )}
    </div>
  )
}

function UnlockScreen({
  loading,
  error,
  onUnlock,
}: {
  loading: boolean
  error: string
  onUnlock: (key: string) => Promise<void>
}) {
  const [key, setKey] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (key.trim()) void onUnlock(key)
  }

  return (
    <main className="unlock">
      <div className="unlock-art" aria-hidden="true">
        <span className="orbit orbit-one" />
        <span className="orbit orbit-two" />
        <div className="unlock-monogram">OR</div>
        <p>curate · audit · experiment</p>
      </div>
      <form className="unlock-card" onSubmit={submit}>
        <p className="eyebrow">Restricted operator surface</p>
        <h1>Unlock Assessment Lab</h1>
        <p>
          Enter the development admin access key. It stays in this browser tab
          only.
        </p>
        <label>
          <span>Admin access key</span>
          <input
            type="password"
            autoComplete="current-password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            autoFocus
          />
        </label>
        {error && <div className="notice error">{error}</div>}
        <button className="primary" disabled={loading || !key}>
          {loading ? 'Validating…' : 'Enter console'}
        </button>
        <small>
          The key is validated by FastAPI and never bundled into the client.
        </small>
      </form>
    </main>
  )
}

function NavLink({
  page,
  current,
  children,
}: {
  page: Page
  current: Page
  children: string
}) {
  return (
    <a
      href={`#/${page}`}
      className={page === current ? 'active' : undefined}
      aria-current={page === current ? 'page' : undefined}
    >
      {children}
    </a>
  )
}

function readPage(): Page {
  const value = window.location.hash.replace(/^#\/?/, '')
  return value === 'items' || value === 'simulation' ? value : 'materials'
}

export default App
