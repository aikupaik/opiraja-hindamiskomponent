import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  errorMessage,
  loginAdmin,
  loginErrorMessage,
  type AdminSession,
  type CourseChoice,
} from './api'
import {
  ADMIN_CREDENTIAL_STORAGE_KEY,
  adminCredentialSource,
  clearAdminCredential,
  storeAdminCredential,
  subscribeToAdminCredentialExpiry,
} from './credential'
import { ItemsPage } from './ItemsPage'
import { MaterialsPage } from './MaterialsPage'
import { PlayerDemoPage } from './PlayerDemoPage'
import { SimulationPage } from './SimulationPage'
import './App.css'

type Page = 'materials' | 'items' | 'simulation' | 'player-demo'

function App() {
  const [session, setSession] = useState<AdminSession | null>(null)
  const [unlocking, setUnlocking] = useState(
    () => adminCredentialSource.getCredential() !== null,
  )
  const [unlockError, setUnlockError] = useState('')
  const [page, setPage] = useState<Page>(readPage)
  const [courses, setCourses] = useState<CourseChoice[]>([])
  const [courseError, setCourseError] = useState('')

  useEffect(
    () =>
      subscribeToAdminCredentialExpiry(() => {
        setSession(null)
        setCourses([])
        setUnlocking(false)
        setUnlockError('Your session expired. Enter your credentials again.')
      }),
    [],
  )

  useEffect(() => {
    const onHashChange = () => setPage(readPage())
    window.addEventListener('hashchange', onHashChange)
    if (!window.location.hash) window.location.hash = '/materials'
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    const stored = sessionStorage.getItem(ADMIN_CREDENTIAL_STORAGE_KEY)
    if (!stored) {
      setUnlocking(false)
      return
    }
    const controller = new AbortController()
    setUnlocking(true)
    api<AdminSession>('/api/v1/admin/session', { signal: controller.signal })
      .then((validated) => {
        setSession(validated)
        setUnlockError('')
      })
      .catch((caught: unknown) => {
        clearAdminCredential()
        setSession(null)
        setUnlockError(loginErrorMessage(caught))
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
      signal: controller.signal,
    })
      .then(setCourses)
      .catch((caught: unknown) => setCourseError(errorMessage(caught)))
    return () => controller.abort()
  }, [session])

  async function unlock(key: string) {
    setUnlocking(true)
    setUnlockError('')
    try {
      const loggedIn = await loginAdmin(key)
      storeAdminCredential(loggedIn.access_token)
      setSession(loggedIn.session)
    } catch (caught) {
      clearAdminCredential()
      setUnlockError(loginErrorMessage(caught))
      setSession(null)
    } finally {
      setUnlocking(false)
    }
  }

  function lock() {
    clearAdminCredential()
    setSession(null)
    setCourses([])
    setUnlockError('')
  }

  async function refreshCourses() {
    const next = await api<CourseChoice[]>('/api/v1/admin/courses')
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
          <NavLink page="player-demo" current={page}>
            Player demo
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
          courses={courses}
          refreshCourses={refreshCourses}
        />
      )}
      {page === 'items' && (
        <ItemsPage courses={courses} />
      )}
      {page === 'simulation' && (
        <SimulationPage
          courses={courses}
          maxGraphNodes={session.max_graph_nodes}
        />
      )}
      {page === 'player-demo' && (
        <PlayerDemoPage
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
          Enter the development admin access key. It is exchanged for a
          browser-tab session and is not stored.
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
          The key is validated by FastAPI and only the signed session token is
          retained in this tab.
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
  return value === 'items' || value === 'simulation' || value === 'player-demo'
    ? value
    : 'materials'
}

export default App
