import { apiClient } from './client'
import { ApiError, ASSESS_TIMEOUT_MS, isRecord, toApiError } from './routes'
import type { AssessResponse, BatchRequest, BatchResponse, BatchResult } from './types'

const BATCH_PATH = '/api/v1/routes/assess-batch/'

/** Reject payloads that do not have the shape the UI relies on, instead of crashing while rendering. */
export function parseBatchResponse(data: unknown): BatchResponse {
  const bad = () => new ApiError('unexpected', 'The server returned a response this app cannot read.')
  if (!isRecord(data) || !Array.isArray(data.routes) || !Array.isArray(data.results) || !isRecord(data.method) || !isRecord(data.diagnostics)) {
    throw bad()
  }
  for (const route of data.routes) {
    if (!isRecord(route) || typeof route.id !== 'string' || !isRecord(route.geometry) || !Array.isArray(route.geometry.coordinates)) throw bad()
  }
  for (const result of data.results) {
    if (!isRecord(result) || typeof result.ok !== 'boolean' || typeof result.departure_datetime !== 'string') throw bad()
    if (result.ok && (!isRecord(result.recommendation) || !Array.isArray(result.routes) || !Array.isArray(result.notes))) throw bad()
    if (!result.ok && !isRecord(result.error)) throw bad()
  }
  return data as unknown as BatchResponse
}

/** POST one trip with several departures. Routes are planned and weather fetched once on the server. */
export async function assessBatch(request: BatchRequest, signal?: AbortSignal): Promise<BatchResponse> {
  try {
    const { data } = await apiClient.post<unknown>(BATCH_PATH, request, { signal, timeout: ASSESS_TIMEOUT_MS })
    return parseBatchResponse(data)
  } catch (err) {
    throw toApiError(err)
  }
}

/**
 * Rebuild the single-departure response shape for one successful batch result, re-attaching the shared
 * geometry by route id. Everything else comes from the result untouched, so no value is computed here.
 */
export function expandBatchResult(batch: BatchResponse, result: Extract<BatchResult, { ok: true }>): AssessResponse {
  const geometry = new Map(batch.routes.map((r) => [r.id, r.geometry]))
  return {
    api_version: batch.api_version,
    request: {
      origin: batch.request.origin,
      destination: batch.request.destination,
      departure_datetime: result.departure_datetime,
      departure_datetime_input: result.departure_datetime_input,
      load_lb: batch.request.load_lb,
      checkpoint_interval_miles: batch.request.checkpoint_interval_miles,
    },
    units: batch.units,
    risk_levels: batch.risk_levels,
    recommendation: result.recommendation,
    method: { ...batch.method, notes: result.notes },
    routes: result.routes.map((route) => {
      const shared = geometry.get(route.id)
      if (!shared) throw new ApiError('unexpected', 'The server returned a route without geometry.')
      return { ...route, geometry: shared }
    }),
  }
}
