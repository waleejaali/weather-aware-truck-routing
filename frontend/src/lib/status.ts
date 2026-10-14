import type { RecommendationStatus } from '../api/types'

export type Tone = 'success' | 'caution' | 'danger' | 'neutral'

export interface StatusInfo {
  title: string
  tone: Tone
  note: string
  hasRecommendation: boolean
}

const INFO: Record<RecommendationStatus, StatusInfo> = {
  recommended: {
    title: 'Recommended route',
    tone: 'success',
    note: '', // backend explanation already includes the safety caveat
    hasRecommendation: true,
  },
  recommended_incomplete_weather: {
    title: 'Recommended, but weather data is incomplete',
    tone: 'caution',
    note: 'Some weather data is missing along the recommended route, so its real risk may be higher than shown.',
    hasRecommendation: true,
  },
  no_safe_route: {
    title: 'No safe route for this departure',
    tone: 'danger',
    note: 'Every route has at least one No Travel checkpoint for this load. Try another departure time.',
    hasRecommendation: false,
  },
  insufficient_weather_data: {
    title: 'Not enough weather data to recommend a route',
    tone: 'neutral',
    note: 'Missing weather is not safe weather. No route is recommended until enough of the trip has forecast data.',
    hasRecommendation: false,
  },
}

export function statusInfo(status: RecommendationStatus): StatusInfo {
  return INFO[status]
}

const SOURCE_LABELS: Record<string, string> = {
  baseline: 'Baseline route',
  shortest_preference: 'Shortest-distance route',
  via_waypoint: 'Alternate via waypoint',
  provider_alternative: 'Provider alternative',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, ' ')
}
