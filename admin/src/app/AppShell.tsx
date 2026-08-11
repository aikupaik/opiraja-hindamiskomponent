import type { ReactNode } from 'react'
import type { AdminSession } from '../shared/api/adminApi'
import { routes, type AdminRouteId } from './routeConfig'
import { FeatureNavigation, TopBar } from '../shared/layout/TopBar'
import '../shared/styles/featureLayouts.css'

export function AppShell({ session, route, courseError, onLock, children }: { session: AdminSession; route: AdminRouteId; courseError: string; onLock: () => void; children: ReactNode }) {
  return <div className="app-shell"><TopBar activeArea={routes[route].area} operator={session.subject} onLock={onLock} /><FeatureNavigation route={route} />{courseError && <div className="global-error" role="alert">{courseError}</div>}{children}</div>
}
