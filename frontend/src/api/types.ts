// Types for POST /api/v1/routes/assess/. They mirror backend/trips/presenters.py and serializers.py.

export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type RecommendationStatus =
  | 'recommended'
  | 'recommended_incomplete_weather'
  | 'no_safe_route'
  | 'insufficient_weather_data'

export type WeatherStatus = 'complete' | 'partial' | 'unavailable'

export type CheckpointInterval = 10 | 25 | 50
export const CHECKPOINT_INTERVALS: readonly CheckpointInterval[] = [10, 25, 50]

export interface Point {
  latitude: number
  longitude: number
}

/** Request body the backend expects. departure_datetime must carry a UTC offset. */
export interface AssessRequest {
  origin: Point
  destination: Point
  departure_datetime: string
  load_lb: number
  checkpoint_interval_miles: CheckpointInterval
}

export interface RiskLegendEntry {
  key: RiskKey
  label: string
  score: number
}

export interface Recommendation {
  status: RecommendationStatus
  recommended_route_id: string | null
  explanation: string
}

export interface Attribution {
  text: string
  url: string
  license: string
  license_url: string
}

export interface Method {
  wind_metric: 'sustained' | 'gust'
  checkpoint_interval_miles: number
  min_weather_coverage_percent: number
  assumptions: string[]
  routing: {
    provider: string
    profile: string
    status: 'complete' | 'partial'
    requested_routes: number
    returned_routes: number
    notes: string[]
  }
  weather: { provider: string; attribution: Attribution }
  notes: string[]
}

export interface RiskMiles {
  low: number
  moderate: number
  high: number
  severe: number
  no_travel: number
  unknown: number
}

export interface RiskSummary {
  miles: RiskMiles
  average_score: number | null
  weather_coverage_percent: number
  weather_data_complete: boolean
  max_risk_level: RiskKey | null
  no_travel_checkpoints: number
}

export interface CheckpointWeather {
  wind_speed_mph: number | null
  wind_gust_mph: number | null
  rain_in_per_hr: number | null
  snow_in_per_hr: number | null
  wind_used_mph: number | null
}

export interface CheckpointRisk {
  combined: RiskKey | null
  wind: RiskKey | null
  rain: RiskKey | null
  snow: RiskKey | null
  load_override: RiskKey | null
  reasons: string[]
}

export interface Checkpoint {
  index: number
  distance_miles: number
  segment_miles: number
  latitude: number
  longitude: number
  eta: string
  weather_status: WeatherStatus
  weather_missing_reason: string | null
  weather: CheckpointWeather
  risk: CheckpointRisk
}

export interface RouteAssessment {
  id: string
  source: string
  rank: number
  recommended: boolean
  eligible: boolean
  ineligible_reason: string | null
  distance_miles: number
  duration_seconds: number
  duration_text: string
  departure_datetime: string
  arrival_datetime: string
  /** GeoJSON LineString: coordinates are [longitude, latitude]. */
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  risk_summary: RiskSummary
  ranking: {
    keys: {
      no_travel_miles: number
      weather_data_complete: boolean
      severe_miles: number
      high_miles: number
      average_score: number | null
      duration_seconds: number
    }
    explanation: string
  }
  checkpoints: Checkpoint[]
}

export interface AssessResponse {
  api_version: string
  request: {
    origin: Point
    destination: Point
    departure_datetime: string
    departure_datetime_input: string
    load_lb: number
    checkpoint_interval_miles: number
  }
  units: Record<string, string>
  risk_levels: RiskLegendEntry[]
  recommendation: Recommendation
  method: Method
  routes: RouteAssessment[]
}

/** Which hazard colours the map corridor and checkpoint markers. */
export type ColorBy = 'combined' | 'wind' | 'rain' | 'snow'

// ---- POST /api/v1/routes/assess-batch/ ---------------------------------------------------------------

/** One trip, several departures. Mirrors backend/trips/serializers.py BatchRequestSerializer. */
export interface BatchRequest {
  origin: Point
  destination: Point
  departure_datetimes: string[]
  load_lb: number
  checkpoint_interval_miles: CheckpointInterval
}

/** Route geometry and totals are the same for every departure, so the batch sends them once. */
export interface SharedRoute {
  id: string
  source: string
  distance_miles: number
  duration_seconds: number
  geometry: RouteAssessment['geometry']
}

export type BatchRouteAssessment = Omit<RouteAssessment, 'geometry'>

interface BatchResultBase {
  index: number
  departure_datetime: string
  departure_datetime_input: string
}

export type BatchResult =
  | (BatchResultBase & { ok: true; recommendation: Recommendation; notes: string[]; routes: BatchRouteAssessment[] })
  | (BatchResultBase & { ok: false; error: { code: string; message: string } })

export interface BatchResponse {
  api_version: string
  generated_at: string
  request: {
    origin: Point
    destination: Point
    load_lb: number
    checkpoint_interval_miles: number
    departure_datetimes: string[]
  }
  units: Record<string, string>
  risk_levels: RiskLegendEntry[]
  method: Omit<Method, 'notes'>
  diagnostics: {
    route_cache: 'hit' | 'miss'
    routing_provider_requests: number | null
    weather_provider_requests: number | null
  }
  routes: SharedRoute[]
  results: BatchResult[]
}
