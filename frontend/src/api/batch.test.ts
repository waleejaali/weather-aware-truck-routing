import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeBatch } from '../test/fixtures'
import { assessBatch, expandBatchResult, parseBatchResponse } from './batch'
import type { BatchRequest } from './types'

vi.mock('./client', () => ({ apiClient: { post: vi.fn() } }))
import { apiClient } from './client'

const post = vi.mocked(apiClient.post)
const REQUEST: BatchRequest = {
  origin: { latitude: 34.0522, longitude: -118.2437 },
  destination: { latitude: 32.7767, longitude: -96.797 },
  departure_datetimes: ['2026-10-14T08:00:00-07:00', '2026-10-14T14:00:00-07:00', '2026-10-14T20:00:00-07:00'],
  load_lb: 42000,
  checkpoint_interval_miles: 25,
}

function httpError(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  return new AxiosError(`HTTP ${status}`, 'ERR_BAD_RESPONSE', config, {}, { status, data, statusText: '', headers: {}, config } as AxiosResponse)
}

// Keep the braces: a returned value from beforeEach is treated as a teardown hook.
beforeEach(() => {
  post.mockReset()
})

describe('assessBatch', () => {
  it('POSTs the exact batch body to /api/v1/routes/assess-batch/ with a long timeout', async () => {
    post.mockResolvedValue({ data: makeBatch(REQUEST) })
    const controller = new AbortController()
    const result = await assessBatch(REQUEST, controller.signal)
    const [url, body, config] = post.mock.calls[0]
    expect(url).toBe('/api/v1/routes/assess-batch/')
    expect(body).toEqual(REQUEST)
    expect(Object.keys(body as object).sort()).toEqual(['checkpoint_interval_miles', 'departure_datetimes', 'destination', 'load_lb', 'origin'])
    expect(config).toMatchObject({ signal: controller.signal })
    expect((config as { timeout: number }).timeout).toBeGreaterThan(60_000)
    expect(result.results).toHaveLength(3)
  })

  it('maps backend errors with the same rules as the single endpoint', async () => {
    post.mockImplementation(() =>
      Promise.reject(httpError(400, { error: { code: 'validation_error', message: 'The request is invalid.', fields: { 'departure_datetimes.1': ['Include a UTC offset.'] } } })),
    )
    await expect(assessBatch(REQUEST)).rejects.toMatchObject({ kind: 'validation', fields: { 'departure_datetimes.1': ['Include a UTC offset.'] } })

    post.mockImplementation(() => Promise.reject(httpError(504, { error: { code: 'weather_timeout', message: 'The weather service did not respond in time.' } })))
    await expect(assessBatch(REQUEST)).rejects.toMatchObject({ kind: 'provider', retryable: true, message: 'The weather service did not respond in time.' })

    post.mockImplementation(() => Promise.reject(new AxiosError('Network Error', 'ERR_NETWORK')))
    await expect(assessBatch(REQUEST)).rejects.toMatchObject({ kind: 'network' })
  })

  it('rejects malformed batch responses instead of crashing while rendering', async () => {
    const good = makeBatch(REQUEST)
    const broken = [
      null,
      {},
      { ...good, results: 'nope' },
      { ...good, diagnostics: null },
      { ...good, routes: [{ id: 'route-1' }] },
      { ...good, results: [{ ok: true, departure_datetime: 'x' }] },
      { ...good, results: [{ ok: false, departure_datetime: 'x' }] },
    ]
    for (const data of broken) {
      post.mockResolvedValueOnce({ data })
      await expect(assessBatch(REQUEST)).rejects.toMatchObject({ kind: 'unexpected' })
    }
  })
})

describe('expandBatchResult', () => {
  const batch = makeBatch(REQUEST, (i) => (i === 1 ? 'no_safe_route' : 'recommended'))
  const ok = (i: number) => {
    const r = batch.results[i]
    if (!r.ok) throw new Error('fixture should be ok')
    return r
  }

  it('re-attaches the shared geometry by route id and leaves every other value untouched', () => {
    const expanded = expandBatchResult(batch, ok(0))
    expect(expanded.routes).toHaveLength(3)
    for (const route of expanded.routes) {
      const shared = batch.routes.find((s) => s.id === route.id)!
      expect(route.geometry).toBe(shared.geometry)
      const { geometry: _geometry, ...rest } = route
      expect(rest).toEqual(ok(0).routes.find((r) => r.id === route.id))
    }
  })

  it("identifies the departure and carries that departure's own recommendation", () => {
    const second = expandBatchResult(batch, ok(1))
    expect(second.request.departure_datetime).toBe(ok(1).departure_datetime)
    expect(second.request.departure_datetime_input).toBe(REQUEST.departure_datetimes[1])
    expect(second.recommendation.status).toBe('no_safe_route')
    expect(second.recommendation.recommended_route_id).toBeNull()
    expect(expandBatchResult(batch, ok(0)).recommendation.status).toBe('recommended')
  })

  it('reuses shared trip fields and method, with the per-departure notes', () => {
    const e = expandBatchResult(batch, ok(0))
    expect(e.request.load_lb).toBe(42000)
    expect(e.method.assumptions).toEqual(batch.method.assumptions)
    expect(e.method.notes).toEqual(ok(0).notes)
  })

  it('refuses a result that references a route with no geometry', () => {
    const broken = { ...batch, routes: batch.routes.slice(0, 1) }
    expect(() => expandBatchResult(broken, ok(0))).toThrow(/without geometry/)
  })

  it('parses a valid response as-is', () => {
    expect(parseBatchResponse(batch)).toBe(batch)
  })
})
