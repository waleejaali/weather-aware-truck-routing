import { confidentLevel } from './checkpoints'
import type { Checkpoint, ColorBy, RiskKey, RouteAssessment } from '../api/types'

export type LatLng = [number, number]

const EARTH_RADIUS_M = 6_371_008.8

export function haversineMeters(a: LatLng, b: LatLng): number {
  const rad = Math.PI / 180
  const dLat = (b[0] - a[0]) * rad
  const dLon = (b[1] - a[1]) * rad
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

// GeoJSON is [lng, lat] but Leaflet wants [lat, lng].
export function toLatLng(coordinates: readonly [number, number][]): LatLng[] {
  return coordinates.map(([lon, lat]) => [lat, lon])
}

export function cumulativeFractions(path: readonly LatLng[]): number[] {
  const cumulative = [0]
  for (let i = 1; i < path.length; i++) cumulative.push(cumulative[i - 1] + haversineMeters(path[i - 1], path[i]))
  const total = cumulative[cumulative.length - 1] || 1
  return cumulative.map((d) => d / total)
}

function interpolate(path: readonly LatLng[], fractions: readonly number[], f: number): LatLng {
  if (f <= 0) return path[0]
  if (f >= 1) return path[path.length - 1]
  let lo = 1
  let hi = path.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (fractions[mid] < f) lo = mid + 1
    else hi = mid
  }
  const span = fractions[lo] - fractions[lo - 1]
  const t = span === 0 ? 0 : (f - fractions[lo - 1]) / span
  const a = path[lo - 1]
  const b = path[lo]
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
}

export interface RiskSegment {
  checkpointIndex: number
  level: RiskKey | null
  positions: LatLng[]
}

export function levelFor(checkpoint: Checkpoint, colorBy: ColorBy): RiskKey | null {
  return confidentLevel(checkpoint, colorBy)
}

// Each checkpoint covers the road halfway to its neighbours, matching how the backend counts risk miles.
export function riskSegments(route: RouteAssessment, colorBy: ColorBy): RiskSegment[] {
  const path = toLatLng(route.geometry.coordinates)
  const checkpoints = route.checkpoints
  if (path.length < 2 || checkpoints.length === 0) return []
  const fractions = cumulativeFractions(path)
  const total = route.distance_miles || checkpoints[checkpoints.length - 1].distance_miles || 1

  const bounds = [0]
  for (let i = 1; i < checkpoints.length; i++) {
    bounds.push((checkpoints[i - 1].distance_miles + checkpoints[i].distance_miles) / 2 / total)
  }
  bounds.push(1)

  const segments: RiskSegment[] = []
  let i = 0
  for (let k = 0; k < checkpoints.length; k++) {
    const start = Math.min(1, bounds[k])
    const end = Math.min(1, bounds[k + 1])
    const positions: LatLng[] = [interpolate(path, fractions, start)]
    while (i < path.length && fractions[i] <= start) i++
    for (; i < path.length && fractions[i] < end; i++) positions.push(path[i])
    positions.push(interpolate(path, fractions, end))
    segments.push({ checkpointIndex: checkpoints[k].index, level: levelFor(checkpoints[k], colorBy), positions })
  }
  return segments
}

export type Bounds = [LatLng, LatLng]

export function boundsOf(paths: readonly (readonly LatLng[])[]): Bounds | null {
  let minLat = Infinity
  let minLon = Infinity
  let maxLat = -Infinity
  let maxLon = -Infinity
  for (const path of paths) {
    for (const [lat, lon] of path) {
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
      if (lon < minLon) minLon = lon
      if (lon > maxLon) maxLon = lon
    }
  }
  return Number.isFinite(minLat) ? [[minLat, minLon], [maxLat, maxLon]] : null
}
