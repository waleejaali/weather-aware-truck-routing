import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { describe, expect, it } from 'vitest'
import { toApiError } from './routes'

function httpError(status: number, data: unknown = {}): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  const response = { status, data, statusText: '', headers: {}, config } as AxiosResponse
  return new AxiosError(`HTTP ${status}`, 'ERR_BAD_RESPONSE', config, {}, response)
}

describe('toApiError: provider limits and transport problems', () => {
  it('treats HTTP 429 as a retryable "busy" condition, not an unreadable response', () => {
    const e = toApiError(httpError(429, {}))
    expect(e.retryable).toBe(true)
    expect(e.status).toBe(429)
    expect(e.message).toMatch(/busy|too many|try again/i)
  })

  it('uses the backend message for a rate limited provider (503) and keeps it retryable', () => {
    const e = toApiError(httpError(503, { error: { code: 'weather_rate_limited', message: 'The weather service is busy. Try again shortly.' } }))
    expect(e).toMatchObject({ kind: 'provider', code: 'weather_rate_limited' })
    expect(e.retryable).toBe(true)
  })

  it('maps the gateway timeout (504) to a retryable provider error', () => {
    expect(toApiError(httpError(504, { error: { code: 'routing_timeout', message: 'The routing service did not respond in time.' } })).retryable).toBe(true)
  })

  it('does not retry validation errors or missing routes', () => {
    const validation = toApiError(
      httpError(400, { error: { code: 'validation_error', message: 'The request is invalid.', fields: { load_lb: ['Load must be greater than 0.'] } } }),
    )
    expect(validation.kind).toBe('validation')
    expect(validation.retryable).toBe(false)
    expect(validation.fields).toEqual({ load_lb: ['Load must be greater than 0.'] })
    expect(toApiError(httpError(422, { error: { code: 'no_route_found' } })).retryable).toBe(false)
  })

  it('never surfaces a raw non-JSON body such as an HTML error page', () => {
    const e = toApiError(httpError(500, '<html><body>Traceback (most recent call last) secret</body></html>'))
    expect(e.message).not.toMatch(/Traceback|secret|html/i)
  })

  it('handles an error body with the wrong types', () => {
    const e = toApiError(httpError(400, { error: { code: 5, message: { nested: true }, fields: 'nope' } }))
    expect(e.kind).toBe('validation')
    expect(typeof e.message).toBe('string')
  })
})
