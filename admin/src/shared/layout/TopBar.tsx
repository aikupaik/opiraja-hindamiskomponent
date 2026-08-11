import { areas, hrefFor, routes, type AdminAreaId, type AdminRouteId } from '../../app/routeConfig'
import { Button } from '../ui/Button'
import { LockIcon } from '../ui/icons'
import styles from './TopBar.module.css'

export function TopBar({ activeArea, operator, onLock }: { activeArea: AdminAreaId; operator: string; onLock: () => void }) {
  return <header className={styles.topBar}>
    <a className={styles.brand} href={hrefFor('materials')}><span className={styles.mark}>OR</span><span><strong>Hindamislabor</strong><small>Operaatori vaade</small></span></a>
    <nav className={styles.areaNavigation} aria-label="Tootealad">
      {areas.map((area) => <a key={area.id} href={hrefFor(area.routes[0])} className={area.id === activeArea ? styles.active : undefined} aria-current={area.id === activeArea ? 'page' : undefined}><strong>{area.label}</strong><small>{area.description}</small></a>)}
    </nav>
    <div className={styles.operator}><span title="Aktiivne operaator"><i aria-hidden="true" />{operator}</span><Button variant="secondary" leadingIcon={<LockIcon />} type="button" onClick={onLock}>Lukusta</Button></div>
  </header>
}

export function FeatureNavigation({ route }: { route: AdminRouteId }) {
  const active = routes[route]
  const area = areas.find((candidate) => candidate.id === active.area)
  if (!area || area.routes.length < 2) return null
  return <nav className={styles.featureNavigation} aria-label={`${area.label} vaated`}><div>{area.routes.map((routeId) => <a key={routeId} href={hrefFor(routeId)} className={routeId === route ? styles.featureActive : undefined} aria-current={routeId === route ? 'page' : undefined}>{routes[routeId].label}</a>)}</div></nav>
}
