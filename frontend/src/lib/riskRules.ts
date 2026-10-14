import type { RiskKey } from '../api/types'

/**
 * The risk thresholds, as shown on the landing page. These mirror backend/risk/thresholds.py and rules.py
 * (the backend is the source of truth and is covered by its own boundary tests); a frontend test pins this copy.
 */
export interface HazardRule {
  key: 'wind' | 'rain' | 'snow'
  label: string
  unit: string
  /** One band per risk level, in order: Low, Moderate, High, Severe, No Travel. */
  bands: [string, string, string, string, string]
}

export const RULE_LEVELS: RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const HAZARD_RULES: HazardRule[] = [
  { key: 'wind', label: 'Wind', unit: 'mph', bands: ['< 25', '25 to < 35', '35 to < 45', '45 to < 55', '≥ 55'] },
  { key: 'rain', label: 'Rain', unit: 'in/hr', bands: ['< 0.10', '0.10 to < 0.25', '0.25 to < 0.50', '0.50 to 1.00', '> 1.00'] },
  { key: 'snow', label: 'Snow', unit: 'in/hr', bands: ['< 0.5', '0.5 to < 1.0', '1.0 to < 2.0', '2.0 to 3.0', '> 3.0'] },
]

export const LOAD_RULES: string[] = [
  'Wind of 55 mph or more is No Travel for any load.',
  'Wind of 45 to 54 mph with a load over 30,000 lb is No Travel.',
  'Wind of 35 to 44 mph with a load over 40,000 lb is Severe instead of High.',
]
