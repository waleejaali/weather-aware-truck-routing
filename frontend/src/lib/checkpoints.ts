import type { Checkpoint } from '../api/types'

/** A checkpoint worth attention: missing/partial weather, or a combined risk above Low. */
export const isProblem = (c: Checkpoint): boolean => c.weather_status !== 'complete' || (c.risk.combined !== null && c.risk.combined !== 'low')
