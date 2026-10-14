import { AxiosError, CanceledError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeResponse, VALID_REQUEST } from '../test/fixtures'
import { ApiError, assessRoutes, parseAssessResponse } from './routes'

vi.mock('./client', () => ({ apiClient: { post: vi.fn() } }))
import { apiClient } from './client'

const post = vi.mocked(apiClient.post)

function httpError(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  const response = { status, data, statusText: '', headers: {}, config } as AxiosResponse
  return new AxiosError(`HTTP ${status}`, 'ERR_BAD_RESPONSE', config, {}, response)
}

async function failure(): Promise<ApiError> {
  try {
    await assessRoutes(VALID_REQUEST)
  } catch (e) {
    return e as ApiError
  }
  throw new Error('expected assessRoutes to reject')
}

// Braces matter: returning the mock from beforeEach makes Vitest call it as a teardown hook.
beforeEach(() => {
  post.mockReset()
})

// Reject lazily (when called). mockRejectedValue builds the rejected promise up front, which Node reports as unhandled.
const rejectWith = (error: unknown) => post.mockImplementation(() => Promise.reject(error))

describe('assessRoutes', () => {
  it('POSTs the exact request body to /api/v1/routes/assess/ with a long timeout', async () => {
    post.mockResolvedValue({ data: makeResponse() })
    const controller = new AbortController()
    const result = await assessRoutes(VALID_REQUEST, controller.signal)
    expect(post).toHaveBeenCalledTimes(1)
    const [url, body, config] = post.mock.calls[0]
    expect(url).toBe('/api/v1/routes/assess/')
    expect(body).toEqual(VALID_REQUEST)
    expect(config).toMatchObject({ signal: controller.signal })
    expect((config as { timeout: number }).timeout).toBeGreaterThan(60_000)
    expect(result.routes).toHaveLength(3)
  })

  it('maps HTTP 400 to a validation error carrying the backend field messages', async () => {
    rejectWith(httpError(400, { error: { code: 'validation_error', message: 'The request is invalid.', fields: { load_lb: ['Load must be greater than 0.'] } } }),
    )
    const e = await failure()
    expect(e.kind).toBe('validation')
    expect(e.fields).toEqual({ load_lb: ['Load must be greater than 0.'] })
    expect(e.retryable).toBe(false)
  })

  it('maps 422 to a non-retryable no-route error', async () => {
    rejectWith(httpError(422, { error: { code: 'no_route_found', message: 'No drivable route could be found between these points.' } }))
    const e = await failure()
    expect(e.kind).toBe('no_route')
    expect(e.retryable).toBe(false)
  })

  it.each([502, 503, 504])('maps provider failure HTTP %i to a retryable provider error', async (status) => {
    rejectWith(httpError(status, { error: { code: 'weather_failed', message: 'The weather service returned an error.' } }))
    const e = await failure()
    expect(e.kind).toBe('provider')
    expect(e.retryable).toBe(true)
    expect(e.message).toBe('The weather service returned an error.')
    expect(e.status).toBe(status)
  })

  it('maps HTTP 500 to a retryable server error with a generic message', async () => {
    rejectWith(httpError(500, { error: { code: 'internal_error', message: 'An unexpected error occurred.' } }))
    const e = await failure()
    expect(e.kind).toBe('server')
    expect(e.retryable).toBe(true)
  })

  it('maps a missing response to a network error and a timeout code to a timeout error', async () => {
    rejectWith(new AxiosError('Network Error', 'ERR_NETWORK'))
    const network = await failure()
    expect(network.kind).toBe('network')
    expect(network.retryable).toBe(true)

    rejectWith(new AxiosError('timeout', 'ECONNABORTED'))
    expect((await failure()).kind).toBe('timeout')
  })

  it('treats an aborted request as cancelled, not as a failure', async () => {
    rejectWith(new CanceledError('canceled'))
    expect((await failure()).kind).toBe('cancelled')
  })

  it('rejects a 200 response that is not the expected shape instead of crashing later', async () => {
    for (const bad of [null, 'ok', {}, { routes: 'nope', recommendation: {}, method: {} }, { routes: [{ id: 'x' }], recommendation: {}, method: {} }]) {
      post.mockResolvedValueOnce({ data: bad })
      const e = await failure()
      expect(e.kind).toBe('unexpected')
    }
  })

  it('does not echo unknown error bodies verbatim', async () => {
    rejectWith(httpError(418, '<html>teapot</html>'))
    const e = await failure()
    expect(e.kind).toBe('unexpected')
    expect(e.message).not.toContain('<html>')
  })
})

describe('parseAssessResponse', () => {
  it('passes a well-formed response through unchanged', () => {
    const data = makeResponse('insufficient_weather_data')
    expect(parseAssessResponse(data)).toBe(data)
  })
})
