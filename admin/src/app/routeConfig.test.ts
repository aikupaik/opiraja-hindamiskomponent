import { describe, expect, it } from 'vitest'
import { areas, defaultRoute, hrefFor, routeFromHash, routes } from './routeConfig'

describe('admin route configuration', () => {
  it('keeps legacy routes and adds the Observe destination', () => {
    expect(defaultRoute).toBe('materials')
    expect(routeFromHash('#/materials')).toBe('materials')
    expect(routeFromHash('#/items')).toBe('items')
    expect(routeFromHash('#/simulation')).toBe('simulation')
    expect(routeFromHash('#/player-demo')).toBe('player-demo')
    expect(routeFromHash('#/kst-parameters')).toBe('kst-parameters')
    expect(routeFromHash('#/observe')).toBe('observe')
    expect(routeFromHash('#/unknown')).toBe(defaultRoute)
  })

  it('derives the active area and secondary destinations from route metadata', () => {
    expect(routes.materials.area).toBe('build')
    expect(routes.simulation.area).toBe('test')
    expect(routes['kst-parameters'].area).toBe('settings')
    expect(areas.find((area) => area.id === 'build')?.routes).toEqual(['materials', 'items'])
    expect(areas.find((area) => area.id === 'test')?.routes).toEqual(['simulation', 'player-demo'])
    expect(hrefFor('observe')).toBe('#/observe')
  })
})
