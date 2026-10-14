import type { RiskKey } from '../api/types'

export interface RiskMeta {
  key: RiskKey | 'unknown'
  label: string
  /** A shape glyph so level is never conveyed by colour alone. */
  symbol: string
  /** Strong colour for map lines/markers. */
  color: string
  /** Soft background and dark text for badges (contrast >= 4.5:1). */
  bg: string
  fg: string
}

/** Halo colour marking the recommended route (only used when the backend recommends one). */
export const RECOMMENDED_COLOR = '#1d4ed8'

export const RISK_ORDER: readonly RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

const META: Record<RiskKey | 'unknown', RiskMeta> = {
  low: { key: 'low', label: 'Low', symbol: '●', color: '#2e7d32', bg: '#e3f4e6', fg: '#14532d' },
  moderate: { key: 'moderate', label: 'Moderate', symbol: '▲', color: '#f2b100', bg: '#fff3c4', fg: '#5c4300' },
  high: { key: 'high', label: 'High', symbol: '◆', color: '#ef6c00', bg: '#ffe5cc', fg: '#7a2e00' },
  severe: { key: 'severe', label: 'Severe', symbol: '■', color: '#c62828', bg: '#fddede', fg: '#7f1d1d' },
  no_travel: { key: 'no_travel', label: 'No Travel', symbol: '✕', color: '#4a148c', bg: '#ece3f7', fg: '#311b92' },
  unknown: { key: 'unknown', label: 'Unknown', symbol: '?', color: '#78909c', bg: '#e8edf0', fg: '#26343c' },
}

export function riskMeta(level: RiskKey | null | undefined): RiskMeta {
  return level ? META[level] : META.unknown
}

export const ALL_RISK_META: RiskMeta[] = [...RISK_ORDER.map((k) => META[k]), META.unknown]
