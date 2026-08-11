import type { KstConfiguration } from '../../shared/api/adminApi'

export type CalculatedLimit = { nodes: number; floor: number; cap: number }

export function calculateLimits(configuration: KstConfiguration, maxGraphNodes: number): CalculatedLimit[] {
  return Array.from({ length: Math.max(0, maxGraphNodes) }, (_, index) => {
    const nodes = index + 1
    const floor = Math.min(
      Math.max(configuration.reliability_floor.minimum, Math.ceil(configuration.reliability_floor.multiplier * nodes)),
      configuration.reliability_floor.maximum,
    )
    return {
      nodes,
      floor,
      cap: Math.ceil(Math.max(configuration.safety_cap.node_multiplier * nodes, floor + configuration.safety_cap.minimum_above_floor)),
    }
  })
}
