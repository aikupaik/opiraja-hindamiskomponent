export type AdminAreaId = 'build' | 'observe' | 'test' | 'settings'

export type AdminRouteId =
  | 'materials'
  | 'items'
  | 'observe'
  | 'simulation'
  | 'player-demo'
  | 'kst-parameters'

export type AdminRoute = {
  id: AdminRouteId
  area: AdminAreaId
  hash: `/${AdminRouteId}`
  label: string
  description: string
}

export type AdminArea = {
  id: AdminAreaId
  label: string
  description: string
  routes: readonly AdminRouteId[]
}

export const routes: Record<AdminRouteId, AdminRoute> = {
  materials: { id: 'materials', area: 'build', hash: '/materials', label: 'Materjalid', description: 'Materjalid ja reeglid' },
  items: { id: 'items', area: 'build', hash: '/items', label: 'Küsimused', description: 'Materjalid ja reeglid' },
  observe: { id: 'observe', area: 'observe', hash: '/observe', label: 'Süsteem ja kvaliteet', description: 'Süsteem ja kvaliteet' },
  simulation: { id: 'simulation', area: 'test', hash: '/simulation', label: 'Simulatsioon', description: 'Katsed' },
  'player-demo': { id: 'player-demo', area: 'test', hash: '/player-demo', label: 'Testimängija', description: 'Katsed' },
  'kst-parameters': { id: 'kst-parameters', area: 'settings', hash: '/kst-parameters', label: 'KST parameetrid', description: 'Ligipääs ja süsteem' },
}

export const areas: readonly AdminArea[] = [
  { id: 'build', label: 'Koosta', description: 'Materjalid ja reeglid', routes: ['materials', 'items'] },
  { id: 'observe', label: 'Jälgi', description: 'Süsteem ja kvaliteet', routes: ['observe'] },
  { id: 'test', label: 'Testi', description: 'Katsed', routes: ['simulation', 'player-demo'] },
  { id: 'settings', label: 'Seaded', description: 'Ligipääs ja süsteem', routes: ['kst-parameters'] },
]

export const defaultRoute: AdminRouteId = 'materials'

export function routeFromHash(hash = window.location.hash): AdminRouteId {
  const route = hash.replace(/^#/, '').replace(/^\//, '')
  return route in routes ? route as AdminRouteId : defaultRoute
}

export function hrefFor(route: AdminRouteId): `#/${AdminRouteId}` {
  return `#${routes[route].hash}`
}
