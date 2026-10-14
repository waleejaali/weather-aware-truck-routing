import axios, { isAxiosError } from 'axios'
import { apiClient } from './client'
import type { AssessRequest, AssessResponse } from './types'

export type ApiErrorKind =
  | 'validation' // 400
  | 'no_route' // 422
  | 'provider' // 502/503/504
  | 'server' // 500
  | 'network'
  | 'timeout'
  | 'unexpected'
  | 'cancelled'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status?: number
  readonly code?: string
  readonly fields?: Record<string, string[]>

  constructor(kind: ApiErrorKind, message: string, extra: { status?: number; code?: string; fields?: Record<string, string[]> } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = extra.status
    this.code = extra.code
    this.fields = extra.fields
  }

  get retryable(): boolean {
    return this.kind === 'provider' || this.kind === 'server' || this.kind === 'network' || this.kind === 'timeout'
  }
}

const ASSESS_PATH = '/api/v1/routes/assess/'
// Route planning plus weather lookups can take well past the default client timeout.
export const ASSESS_TIMEOUT_MS = 120_000

interface ErrorBody {
  error?: { code?: unknown; message?: unknown; fields?: unknown }
}

function readErrorBody(data: unknown): { code?: string; message?: string; fields?: Record<string, string[]> } {
  const error = (data as ErrorBody | null | undefined)?.error
  if (!error || typeof error !== 'object') return {}
  const fields: Record<string, string[]> = {}
  if (error.fields && typeof error.fields === 'object') {
    for (const [key, value] of Object.entries(error.fields as Record<string, unknown>)) {
      fields[key] = Array.isArray(value) ? value.map(String) : [String(value)]
    }
  }
  return {
    code: typeof error.code === 'string' ? error.code : undefined,
    message: typeof error.message === 'string' ? error.message : undefined,
    fields: Object.keys(fields).length > 0 ? fields : undefined,
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  if (axios.isCancel(err)) return new ApiError('cancelled', 'The request was cancelled.')
  if (!isAxiosError(err)) return new ApiError('unexpected', 'Something went wrong while assessing routes.')

  if (!err.response) {
    if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
      return new ApiError('timeout', 'The server took too long to respond. Try again.')
    }
    return new ApiError('network', 'Could not reach the server. Check your connection and that the backend is running.')
  }

  const { status, data } = err.response
  const body = readErrorBody(data)
  const extra = { status, code: body.code, fields: body.fields }
  if (status === 400) return new ApiError('validation', body.message ?? 'The request was not valid.', extra)
  if (status === 422) {
    return new ApiError('no_route', body.message ?? 'No drivable route could be found between these points.', extra)
  }
  if (status === 429) {
    return new ApiError('provider', body.message ?? 'The service is busy. Try again shortly.', extra)
  }
  if (status === 502 || status === 503 || status === 504) {
    return new ApiError('provider', body.message ?? 'A routing or weather service is unavailable. Try again shortly.', extra)
  }
  if (status >= 500) return new ApiError('server', 'The server hit an unexpected error. Try again.', extra)
  return new ApiError('unexpected', body.message ?? `Unexpected response (HTTP ${status}).`, extra)
}

export const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

export function parseAssessResponse(data: unknown): AssessResponse {
  const bad = () => new ApiError('unexpected', 'The server returned a response this app cannot read.')
  if (!isRecord(data) || !Array.isArray(data.routes) || !isRecord(data.recommendation) || !isRecord(data.method)) {
    throw bad()
  }
  for (const route of data.routes) {
    if (
      !isRecord(route) ||
      typeof route.id !== 'string' ||
      !isRecord(route.geometry) ||
      !Array.isArray(route.geometry.coordinates) ||
      !Array.isArray(route.checkpoints) ||
      !isRecord(route.risk_summary) ||
      !isRecord(route.risk_summary.miles)
    ) {
      throw bad()
    }
  }
  return data as unknown as AssessResponse
}

export async function assessRoutes(request: AssessRequest, signal?: AbortSignal): Promise<AssessResponse> {
  try {
    const { data } = await apiClient.post<unknown>(ASSESS_PATH, request, { signal, timeout: ASSESS_TIMEOUT_MS })
    return parseAssessResponse(data)
  } catch (err) {
    throw toApiError(err)
  }
}
