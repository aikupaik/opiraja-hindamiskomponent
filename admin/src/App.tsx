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
import { KstParametersPage } from './KstParametersPage'
import './App.css'

type Page = 'materials' | 'items' | 'simulation' | 'player-demo' | 'kst-parameters'

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
        setUnlockError('Seans aegus. Sisesta ligipääsuvõti uuesti.')
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
            <strong>Hindamislabor</strong>
            <small>Operaatori vaade</small>
          </span>
        </a>
        <nav aria-label="Administraatori jaotised">
          <NavLink page="materials" current={page}>
            Materjalid
          </NavLink>
          <NavLink page="items" current={page}>
            Küsimused
          </NavLink>
          <NavLink page="simulation" current={page}>
            Simulatsioon
          </NavLink>
          <NavLink page="kst-parameters" current={page}>
            KST parameetrid
          </NavLink>
          <NavLink page="player-demo" current={page}>
            Testimängija
          </NavLink>
        </nav>
        <div className="operator">
          <span>
            <i />
            {session.subject}
          </span>
          <button type="button" className="lock-button" onClick={lock}>
            Lukusta
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
      {page === 'kst-parameters' && (
        <KstParametersPage maxGraphNodes={session.max_graph_nodes} />
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
      </div>
      <form className="unlock-card" onSubmit={submit}>
        <p className="eyebrow">Piiratud ligipääsuga operaatorivaade</p>
        <h1>Ava hindamislabor</h1>
        <label>
          <span>Administraatori ligipääsuvõti</span>
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
          {loading ? 'Kontrollin…' : 'Sisene'}
        </button>
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
  return value === 'items' || value === 'simulation' || value === 'player-demo' || value === 'kst-parameters'
    ? value
    : 'materials'
}

export default App
