import type {
  AssessRequest,
  BatchRequest,
  BatchResponse,
  AssessResponse,
  Checkpoint,
  RecommendationStatus,
  RiskKey,
  RouteAssessment,
} from '../api/types'

/** Test data shaped like the real API response. These are fixtures, not real routes or weather. */
export function makeCheckpoint(index: number, over: Partial<Checkpoint> = {}): Checkpoint {
  return {
    index,
    distance_miles: index * 25,
    segment_miles: 25,
    latitude: 34 - index * 0.5,
    longitude: -118 + index * 2,
    eta: `2026-10-14T${String(15 + index).padStart(2, '0')}:00:00Z`,
    weather_status: 'complete',
    weather_missing_reason: null,
    weather: { wind_speed_mph: 8.2, wind_gust_mph: 11.6, rain_in_per_hr: 0.02, snow_in_per_hr: 0, wind_used_mph: 8.2 },
    risk: { combined: 'low', wind: 'low', rain: 'low', snow: 'low', load_override: null, reasons: [] },
    ...over,
  }
}

export const MISSING_CHECKPOINT = (index: number): Checkpoint =>
  makeCheckpoint(index, {
    weather_status: 'unavailable',
    weather_missing_reason: 'arrival 2026-11-01 00:00 UTC is beyond the forecast horizon (2026-07-12 to 2026-10-28 UTC)',
    weather: { wind_speed_mph: null, wind_gust_mph: null, rain_in_per_hr: null, snow_in_per_hr: null, wind_used_mph: null },
    risk: { combined: null, wind: null, rain: null, snow: null, load_override: null, reasons: [] },
  })

export function makeRoute(n: number, over: Partial<RouteAssessment> = {}): RouteAssessment {
  const checkpoints = [makeCheckpoint(0), makeCheckpoint(1), makeCheckpoint(2)]
  return {
    id: `route-${n}`,
    source: n === 1 ? 'baseline' : 'via_waypoint',
    rank: n,
    recommended: n === 1,
    eligible: true,
    ineligible_reason: null,
    distance_miles: 1400 + n * 10,
    duration_seconds: 120_000 + n * 600,
    duration_text: `${33 + n} h 9 min`,
    departure_datetime: '2026-10-14T15:00:00Z',
    arrival_datetime: '2026-10-16T00:09:00Z',
    geometry: {
      type: 'LineString',
      coordinates: [
        [-118.2437, 34.0522],
        [-110, 33.5],
        [-96.797, 32.7767],
      ],
    },
    risk_summary: {
      miles: { low: 1400, moderate: 25, high: 0, severe: 0, no_travel: 0, unknown: 0 },
      average_score: 0.017,
      weather_coverage_percent: 100,
      weather_data_complete: true,
      max_risk_level: 'moderate',
      no_travel_checkpoints: 0,
    },
    ranking: {
      keys: {
        no_travel_miles: 0,
        weather_data_complete: true,
        severe_miles: 0,
        high_miles: 0,
        average_score: 0.017,
        duration_seconds: 120_000,
      },
      explanation: `Ranked ${n}: test explanation.`,
    },
    checkpoints,
    ...over,
  }
}

export function makeResponse(
  status: RecommendationStatus = 'recommended',
  over: Partial<AssessResponse> = {},
): AssessResponse {
  const recommendedId = status === 'recommended' || status === 'recommended_incomplete_weather' ? 'route-1' : null
  return {
    api_version: 'v1',
    request: {
      origin: { latitude: 34.0522, longitude: -118.2437 },
      destination: { latitude: 32.7767, longitude: -96.797 },
      departure_datetime: '2026-10-14T15:00:00Z',
      departure_datetime_input: '2026-10-14T08:00:00-07:00',
      load_lb: 42000,
      checkpoint_interval_miles: 25,
    },
    units: { distance: 'mi' },
    risk_levels: [],
    recommendation: {
      status,
      recommended_route_id: recommendedId,
      explanation: `Backend explanation for ${status}.`,
    },
    method: {
      wind_metric: 'sustained',
      checkpoint_interval_miles: 25,
      min_weather_coverage_percent: 80,
      assumptions: ['Weather is sampled at checkpoints about every 25 miles.'],
      routing: { provider: 'openrouteservice', profile: 'driving-hgv', status: 'complete', requested_routes: 3, returned_routes: 3, notes: [] },
      weather: {
        provider: 'open-meteo',
        attribution: { text: 'Weather data by Open-Meteo.com', url: 'https://open-meteo.com/', license: 'CC BY 4.0', license_url: 'https://creativecommons.org/licenses/by/4.0/' },
      },
      notes: [],
    },
    routes: [makeRoute(1, { recommended: recommendedId === 'route-1' }), makeRoute(2, { recommended: false }), makeRoute(3, { recommended: false })],
    ...over,
  }
}

export const VALID_REQUEST: AssessRequest = {
  origin: { latitude: 34.0522, longitude: -118.2437 },
  destination: { latitude: 32.7767, longitude: -96.797 },
  departure_datetime: '2026-10-14T08:00:00-07:00',
  load_lb: 42000,
  checkpoint_interval_miles: 25,
}

export const LEVELS: RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

/** A batch response for the departures in `request`. statusFor(i) gives each result's status, or 'error' for a failed one. */
export function makeBatch(
  request: BatchRequest,
  statusFor: (index: number) => RecommendationStatus | 'error' = () => 'recommended',
  diagnostics: BatchResponse['diagnostics'] = { route_cache: 'miss', routing_provider_requests: 4, weather_provider_requests: 4 },
): BatchResponse {
  const template = makeResponse('recommended')
  return {
    api_version: 'v1',
    generated_at: '2026-10-12T12:00:00Z',
    request: {
      origin: request.origin,
      destination: request.destination,
      load_lb: request.load_lb,
      checkpoint_interval_miles: request.checkpoint_interval_miles,
      departure_datetimes: request.departure_datetimes,
    },
    units: template.units,
    risk_levels: template.risk_levels,
    method: {
      wind_metric: template.method.wind_metric,
      checkpoint_interval_miles: template.method.checkpoint_interval_miles,
      min_weather_coverage_percent: template.method.min_weather_coverage_percent,
      assumptions: template.method.assumptions,
      routing: template.method.routing,
      weather: template.method.weather,
    },
    diagnostics,
    routes: template.routes.map((r) => ({
      id: r.id,
      source: r.source,
      distance_miles: r.distance_miles,
      duration_seconds: r.duration_seconds,
      geometry: r.geometry,
    })),
    results: request.departure_datetimes.map((departure, index) => {
      const base = {
        index,
        departure_datetime: new Date(departure).toISOString().replace('.000Z', 'Z'),
        departure_datetime_input: departure,
      }
      const status = statusFor(index)
      if (status === 'error') {
        return { ...base, ok: false as const, error: { code: 'assessment_failed', message: 'This departure could not be assessed.' } }
      }
      const response = makeResponse(status)
      return {
        ...base,
        ok: true as const,
        recommendation: response.recommendation,
        notes: [],
        routes: response.routes.map(({ geometry: _geometry, ...rest }) => rest),
      }
    }),
  }
}
