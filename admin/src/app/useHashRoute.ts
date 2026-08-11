import { useEffect, useState } from 'react'
import { defaultRoute, routeFromHash, type AdminRouteId } from './routeConfig'

export function useHashRoute(): AdminRouteId {
  const [route, setRoute] = useState<AdminRouteId>(() => routeFromHash())

  useEffect(() => {
    const updateRoute = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', updateRoute)
    if (!window.location.hash) window.location.hash = `/${defaultRoute}`
    return () => window.removeEventListener('hashchange', updateRoute)
  }, [])

  return route
}
