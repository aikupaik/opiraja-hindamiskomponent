import { useEffect, useState } from 'react'
import {
  api,
  errorMessage,
  loginAdmin,
  loginErrorMessage,
  type AdminSession,
  type CourseChoice,
} from '../shared/api/adminApi'
import {
  ADMIN_CREDENTIAL_STORAGE_KEY,
  adminCredentialSource,
  clearAdminCredential,
  storeAdminCredential,
  subscribeToAdminCredentialExpiry,
} from '../features/auth/credential'
import { UnlockScreen } from '../features/auth/UnlockScreen'
import { MaterialsPage } from '../features/materials/MaterialsPage'
import { ItemsPage } from '../features/items/ItemsPage'
import { SimulationPage } from '../features/experiments/simulation/SimulationPage'
import { PlayerDemoPage } from '../features/experiments/player-demo/PlayerDemoPage'
import { KstParametersPage } from '../features/kst-configuration/KstParametersPage'
import { SystemQualityPage } from '../features/system-quality/SystemQualityPage'
import { AppShell } from './AppShell'
import { useHashRoute } from './useHashRoute'
import { loadCourses } from '../shared/api/courses'

export default function App() {
  const [session, setSession] = useState<AdminSession | null>(null)
  const [unlocking, setUnlocking] = useState(() => adminCredentialSource.getCredential() !== null)
  const [unlockError, setUnlockError] = useState('')
  const route = useHashRoute()
  const [courses, setCourses] = useState<CourseChoice[]>([])
  const [courseError, setCourseError] = useState('')

  useEffect(() => subscribeToAdminCredentialExpiry(() => {
    setSession(null); setCourses([]); setUnlocking(false); setUnlockError('Seans aegus. Sisesta ligipääsuvõti uuesti.')
  }), [])

  useEffect(() => {
    const stored = sessionStorage.getItem(ADMIN_CREDENTIAL_STORAGE_KEY)
    if (!stored) { setUnlocking(false); return }
    const controller = new AbortController()
    setUnlocking(true)
    api<AdminSession>('/api/v1/admin/session', { signal: controller.signal }).then((validated) => {
      setSession(validated); setUnlockError('')
    }).catch((caught: unknown) => {
      clearAdminCredential(); setSession(null); setUnlockError(loginErrorMessage(caught))
    }).finally(() => setUnlocking(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!session) { setCourses([]); return }
    const controller = new AbortController()
    setCourseError('')
    loadCourses(controller.signal).then(setCourses).catch((caught: unknown) => setCourseError(errorMessage(caught)))
    return () => controller.abort()
  }, [session])

  async function unlock(key: string) {
    setUnlocking(true); setUnlockError('')
    try { const loggedIn = await loginAdmin(key); storeAdminCredential(loggedIn.access_token); setSession(loggedIn.session) }
    catch (caught) { clearAdminCredential(); setUnlockError(loginErrorMessage(caught)); setSession(null) }
    finally { setUnlocking(false) }
  }
  function lock() { clearAdminCredential(); setSession(null); setCourses([]); setUnlockError('') }
  async function refreshCourses() { setCourses(await loadCourses()) }

  if (!session) return <UnlockScreen loading={unlocking} error={unlockError} onUnlock={unlock} />
  return <AppShell session={session} route={route} courseError={courseError} onLock={lock}>
    {route === 'materials' && <MaterialsPage courses={courses} refreshCourses={refreshCourses} />}
    {route === 'items' && <ItemsPage courses={courses} />}
    {route === 'observe' && <SystemQualityPage />}
    {route === 'simulation' && <SimulationPage courses={courses} maxGraphNodes={session.max_graph_nodes} />}
    {route === 'player-demo' && <PlayerDemoPage courses={courses} maxGraphNodes={session.max_graph_nodes} />}
    {route === 'kst-parameters' && <KstParametersPage maxGraphNodes={session.max_graph_nodes} />}
  </AppShell>
}
