import { useCallback, useEffect, useRef, useState } from 'react'
import { assessBatch, expandBatchResult } from '../api/batch'
import { ApiError } from '../api/routes'
import type { AssessRequest, AssessResponse, BatchRequest, BatchResponse, RecommendationStatus } from '../api/types'
import { shiftIsoByHours } from '../lib/time'

/**
 * Forecast offsets (hours after the entered departure) assessed together when a trip is submitted: one batch
 * request, one route plan and one weather fetch on the server. Bounded on purpose - not every hour.
 */
export const PREFETCH_OFFSETS: readonly number[] = [0, 6, 12, 18, 24, 30, 36, 42, 48]

/** Weather forecasts are refreshed by the provider through the day, so an old assessment is not shown as current. */
export const STALE_AFTER_MS = 30 * 60 * 1000

export type OffsetEntry =
  | { kind: 'ok'; data: AssessResponse; fetchedAt: number }
  | { kind: 'error'; code: string; message: string; at: number }

export interface BatchStats {
  departures: number
  routeCache: 'hit' | 'miss'
  routingRequests: number | null
  weatherRequests: number | null
}

export interface AssessmentState {
  phase: 'idle' | 'loading' | 'success' | 'error'
  /** The request as submitted by the user (offset 0). */
  base: AssessRequest | null
  /** Every offset assessed (or failed) for this trip. */
  entries: Record<number, OffsetEntry>
  /** The offset whose assessment is displayed. */
  shownOffset: number
  /** The offset being requested, while loading. */
  requestedOffset: number
  error: ApiError | null
  lastBatch: BatchStats | null
}

const INITIAL: AssessmentState = {
  phase: 'idle',
  base: null,
  entries: {},
  shownOffset: 0,
  requestedOffset: 0,
  error: null,
  lastBatch: null,
}

export function isStale(entry: OffsetEntry, now: number = Date.now()): boolean {
  return entry.kind === 'ok' && now - entry.fetchedAt > STALE_AFTER_MS
}

function departureFor(base: AssessRequest, offsetHours: number): string {
  return offsetHours === 0 ? base.departure_datetime : shiftIsoByHours(base.departure_datetime, offsetHours)
}

/** Turn a batch response into per-offset entries, checking each result is for the departure we asked for. */
function toEntries(batch: BatchResponse, offsets: readonly number[], asked: readonly string[], at: number): Record<number, OffsetEntry> {
  if (batch.results.length !== offsets.length) throw new ApiError('unexpected', 'The server returned a different number of results than departures requested.')
  const entries: Record<number, OffsetEntry> = {}
  offsets.forEach((offset, i) => {
    const result = batch.results[i]
    const sameInstant = new Date(result.departure_datetime).getTime() === new Date(asked[i]).getTime()
    if (!sameInstant) {
      entries[offset] = { kind: 'error', code: 'mismatched_departure', message: 'The server answered for a different departure time.', at }
    } else if (result.ok) {
      try {
        entries[offset] = { kind: 'ok', data: expandBatchResult(batch, result), fetchedAt: at }
      } catch (e) {
        entries[offset] = { kind: 'error', code: 'unreadable', message: e instanceof Error ? e.message : 'Unreadable result.', at }
      }
    } else {
      entries[offset] = { kind: 'error', code: result.error.code, message: result.error.message, at }
    }
  })
  return entries
}

/** Request state for trip assessments: bounded batch prefetch, per-offset entries, staleness and retries. */
export function useAssessment() {
  const [state, setState] = useState<AssessmentState>(INITIAL)
  // Event handlers read the latest state through a ref that is updated after each commit (never during render).
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])
  const controller = useRef<AbortController | null>(null)

  const run = useCallback(async (base: AssessRequest, offsets: readonly number[], show: number, isNewTrip: boolean) => {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort

    setState((s) => ({
      ...s,
      phase: 'loading',
      base,
      requestedOffset: show,
      error: null,
      ...(isNewTrip ? { entries: {}, shownOffset: 0, lastBatch: null } : {}),
    }))

    const asked = offsets.map((o) => departureFor(base, o))
    const request: BatchRequest = {
      origin: base.origin,
      destination: base.destination,
      departure_datetimes: asked,
      load_lb: base.load_lb,
      checkpoint_interval_miles: base.checkpoint_interval_miles,
    }
    try {
      const batch = await assessBatch(request, abort.signal)
      const at = Date.now()
      const fresh = toEntries(batch, offsets, asked, at)
      const wanted = fresh[show]
      setState((s) => ({
        ...s,
        entries: { ...s.entries, ...fresh },
        lastBatch: {
          departures: offsets.length,
          routeCache: batch.diagnostics.route_cache,
          routingRequests: batch.diagnostics.routing_provider_requests,
          weatherRequests: batch.diagnostics.weather_provider_requests,
        },
        ...(wanted?.kind === 'ok'
          ? { phase: 'success' as const, shownOffset: show, error: null }
          : { phase: 'error' as const, error: new ApiError('provider', wanted?.kind === 'error' ? wanted.message : 'No result for this departure.') }),
      }))
    } catch (err) {
      const error = err instanceof ApiError ? err : new ApiError('unexpected', 'Something went wrong while assessing routes.')
      if (error.kind === 'cancelled') return // superseded by a newer request
      setState((s) => ({ ...s, phase: 'error', error }))
    }
  }, [])

  /** Assess a new trip: the entered departure plus the bounded set of later departures, in one request. */
  const submit = useCallback((request: AssessRequest) => run(request, PREFETCH_OFFSETS, 0, true), [run])

  /** Show a departure. Fresh results are shown instantly; anything else is requested (routes are reused server-side). */
  const selectOffset = useCallback(
    (offset: number) => {
      const s = stateRef.current
      if (!s.base) return
      const entry = s.entries[offset]
      if (entry?.kind === 'ok' && !isStale(entry)) {
        setState((prev) => ({ ...prev, shownOffset: offset, phase: 'success', error: null }))
        return
      }
      void run(s.base, [offset], offset, false)
    },
    [run],
  )

  const retry = useCallback(() => {
    const s = stateRef.current
    if (!s.base) return
    if (Object.keys(s.entries).length === 0) void run(s.base, PREFETCH_OFFSETS, 0, true)
    else void run(s.base, [s.requestedOffset], s.requestedOffset, false)
  }, [run])

  const shown = state.entries[state.shownOffset]
  const data: AssessResponse | null = shown?.kind === 'ok' ? shown.data : null
  return { state, data, submit, selectOffset, retry }
}

export function statusOf(entry: OffsetEntry): RecommendationStatus | null {
  return entry.kind === 'ok' ? entry.data.recommendation.status : null
}
