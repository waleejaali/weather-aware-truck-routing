import type { RiskKey } from '../api/types'

export interface RiskMeta {
  key: RiskKey | 'unknown'
  label: string
  symbol: string // so risk isn't conveyed by colour alone
  color: string
  bg: string // bg/fg pairs keep badge text at >= 4.5:1 contrast
  fg: string
}

export const RECOMMENDED_COLOR = '#60a5fa'

export const RISK_ORDER: readonly RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

// Dark-theme palette. `color` is for map lines/markers (>= 3:1 on the dark map); bg/fg are badge pairs (>= 4.5:1).
const META: Record<RiskKey | 'unknown', RiskMeta> = {
  low: { key: 'low', label: 'Low', symbol: '●', color: '#34c38f', bg: '#0f3b2a', fg: '#86efac' },
  moderate: { key: 'moderate', label: 'Moderate', symbol: '▲', color: '#f2c230', bg: '#3d3210', fg: '#fde68a' },
  high: { key: 'high', label: 'High', symbol: '◆', color: '#f0883e', bg: '#45250c', fg: '#fdba74' },
  severe: { key: 'severe', label: 'Severe', symbol: '■', color: '#ef4444', bg: '#4a1717', fg: '#fca5a5' },
  no_travel: { key: 'no_travel', label: 'No Travel', symbol: '✕', color: '#a855f7', bg: '#2e1a52', fg: '#d8b4fe' },
  unknown: { key: 'unknown', label: 'Unknown', symbol: '?', color: '#7b8b97', bg: '#26323b', fg: '#cbd5df' },
}

export function riskMeta(level: RiskKey | null | undefined): RiskMeta {
  return level ? META[level] : META.unknown
}

export const ALL_RISK_META: RiskMeta[] = [...RISK_ORDER.map((k) => META[k]), META.unknown]
