import type { Checkpoint, ColorBy, RiskKey } from '../api/types'

/** A checkpoint worth attention: missing/partial weather, or a combined risk above Low. */
export const isProblem = (c: Checkpoint): boolean => c.weather_status !== 'complete' || (c.risk.combined !== null && c.risk.combined !== 'low')

/** Which required measurements are absent at this checkpoint (the wind figure the risk is based on, rain, snow). */
export function missingMeasurements(c: Checkpoint): string[] {
  const missing: string[] = []
  if (c.weather.wind_used_mph === null) missing.push('wind')
  if (c.weather.rain_in_per_hr === null) missing.push('rain')
  if (c.weather.snow_in_per_hr === null) missing.push('snow')
  return missing
}

/**
 * The level a checkpoint can be shown at with confidence. The backend computes the combined level from whatever was
 * measured, so with a measurement missing a "Low" or "Moderate" or "High" only says "at least this", which must not
 * read as a fully known checkpoint. Severe and No Travel stay visible: missing data cannot make those safer.
 * Single-hazard modes are exact, because their own measurement is either present or null.
 */
export function confidentLevel(c: Checkpoint, colorBy: ColorBy = 'combined'): RiskKey | null {
  const level = c.risk[colorBy]
  if (colorBy !== 'combined' || c.weather_status === 'complete') return level
  return level === 'severe' || level === 'no_travel' ? level : null
}

/** True when the combined level is only a lower bound because something was not measured. */
export const isLowerBound = (c: Checkpoint): boolean => c.weather_status === 'partial' && c.risk.combined !== null
