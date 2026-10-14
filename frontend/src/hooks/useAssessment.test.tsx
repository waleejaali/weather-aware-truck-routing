import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { assessBatch } from '../api/batch'
import { ApiError } from '../api/routes'
import type { BatchRequest, BatchResponse } from '../api/types'
import { makeBatch, VALID_REQUEST } from '../test/fixtures'
import { PREFETCH_OFFSETS, STALE_AFTER_MS, useAssessment } from './useAssessment'

vi.mock('../api/batch', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/batch')>()),
  assessBatch: vi.fn(),
}))
const batch = vi.mocked(assessBatch)

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
}
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const HOUR = 3_600_000
const instant = (iso: string) => new Date(iso).getTime()

beforeEach(() => {
  batch.mockReset()
})
afterEach(() => {
  vi.restoreAllMocks()
})

async function submitted() {
  batch.mockImplementation(async (request: BatchRequest) => makeBatch(request))
  const hook = renderHook(() => useAssessment())
  await act(async () => {
    await hook.result.current.submit(VALID_REQUEST)
  })
  return hook
}

describe('useAssessment: requests', () => {
  it('sends one batch whose departures are the entered time plus 0, 6, ... 48 whole hours', async () => {
    await submitted()
    expect(batch).toHaveBeenCalledTimes(1)
    const [request] = batch.mock.calls[0]
    expect(request.departure_datetimes).toHaveLength(PREFETCH_OFFSETS.length)
    request.departure_datetimes.forEach((departure, i) => {
      expect(instant(departure) - instant(VALID_REQUEST.departure_datetime)).toBe(PREFETCH_OFFSETS[i] * HOUR)
    })
    expect(request.departure_datetimes[0]).toBe(VALID_REQUEST.departure_datetime)
    expect(PREFETCH_OFFSETS[PREFETCH_OFFSETS.length - 1]).toBe(48)
    expect(request.departure_datetimes.length).toBeLessThanOrEqual(12) // the backend limit
  })

  it('never lets a request carry a naive (offset-less) departure', async () => {
    await submitted()
    for (const departure of batch.mock.calls[0][0].departure_datetimes) {
      expect(departure).toMatch(/(Z|[+-]\d{2}:\d{2})$/)
    }
  })

  it('serves a prefetched offset from memory and requests anything else as a single departure', async () => {
    const { result } = await submitted()
    act(() => result.current.selectOffset(12))
    expect(result.current.state.shownOffset).toBe(12)
    expect(batch).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.selectOffset(7)
    })
    expect(batch).toHaveBeenCalledTimes(2)
    const [first, second] = [batch.mock.calls[0][0], batch.mock.calls[1][0]]
    expect(second.departure_datetimes).toHaveLength(1)
    expect(instant(second.departure_datetimes[0]) - instant(first.departure_datetimes[0])).toBe(7 * HOUR)
    expect(result.current.state.shownOffset).toBe(7)
  })

  it('does nothing before a trip has been submitted', () => {
    const { result } = renderHook(() => useAssessment())
    act(() => result.current.selectOffset(6))
    act(() => result.current.retry())
    expect(batch).not.toHaveBeenCalled()
    expect(result.current.state.phase).toBe('idle')
    expect(result.current.data).toBeNull()
  })
})

describe('useAssessment: races and cancellation', () => {
  it('keeps the newest selection when an older response arrives later', async () => {
    const { result } = await submitted()
    const slow = deferred<BatchResponse>()
    const fast = deferred<BatchResponse>()
    batch.mockReset()
    batch.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)

    act(() => result.current.selectOffset(7))
    act(() => result.current.selectOffset(9))
    const [slowRequest, fastRequest] = [batch.mock.calls[0][0], batch.mock.calls[1][0]]
    expect(batch.mock.calls[0][1]?.aborted).toBe(true) // the superseded request was cancelled

    await act(async () => fast.resolve(makeBatch(fastRequest)))
    await waitFor(() => expect(result.current.state.shownOffset).toBe(9))
    // The transport ignored the cancellation and still answered; that answer must not replace offset 9.
    await act(async () => slow.resolve(makeBatch(slowRequest)))
    expect(result.current.state.shownOffset).toBe(9)
    expect(result.current.state.phase).toBe('success')
    expect(result.current.state.requestedOffset).toBe(9)
    expect(result.current.state.entries[7]).toBeUndefined()
  })

  it('choosing an already-assessed departure while another request is in flight keeps that choice', async () => {
    const { result } = await submitted()
    const slow = deferred<BatchResponse>()
    batch.mockReset()
    batch.mockReturnValueOnce(slow.promise)
    act(() => result.current.selectOffset(7)) // needs a request
    act(() => result.current.selectOffset(12)) // prefetched: shown immediately
    expect(result.current.state.shownOffset).toBe(12)
    await act(async () => slow.resolve(makeBatch(batch.mock.calls[0][0])))
    expect(result.current.state.shownOffset).toBe(12)
    expect(result.current.state.phase).toBe('success')
  })

  it('ignores a cancelled request instead of reporting an error', async () => {
    const { result } = await submitted()
    const first = deferred<BatchResponse>()
    batch.mockReset()
    batch.mockReturnValueOnce(first.promise).mockImplementationOnce(async (r) => makeBatch(r))
    act(() => result.current.selectOffset(7))
    await act(async () => {
      result.current.selectOffset(9)
    })
    await act(async () => first.reject(new ApiError('cancelled', 'The request was cancelled.')))
    expect(result.current.state.error).toBeNull()
    expect(result.current.state.shownOffset).toBe(9)
  })

  it('does not let a late failure from a superseded request overwrite a newer success', async () => {
    const { result } = await submitted()
    const first = deferred<BatchResponse>()
    batch.mockReset()
    batch.mockReturnValueOnce(first.promise).mockImplementationOnce(async (r) => makeBatch(r))
    act(() => result.current.selectOffset(7))
    await act(async () => {
      result.current.selectOffset(9)
    })
    await act(async () => first.reject(new ApiError('network', 'Could not reach the server.')))
    expect(result.current.state.phase).toBe('success')
    expect(result.current.state.error).toBeNull()
  })

  it('cancels an in-flight request when the component unmounts', async () => {
    const { result, unmount } = await submitted()
    batch.mockReset()
    batch.mockReturnValue(deferred<BatchResponse>().promise)
    act(() => result.current.selectOffset(7))
    const signal = batch.mock.calls[0][1]
    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })

  it('a new trip discards the previous trip results immediately', async () => {
    const { result } = await submitted()
    const pending = deferred<BatchResponse>()
    batch.mockReset()
    batch.mockReturnValueOnce(pending.promise)
    act(() => {
      void result.current.submit({ ...VALID_REQUEST, load_lb: 10_000 })
    })
    expect(result.current.state.entries).toEqual({})
    expect(result.current.data).toBeNull()
    expect(result.current.state.phase).toBe('loading')
  })
})

describe('useAssessment: failures and freshness', () => {
  it('a failed whole request leaves no results and retry repeats the full prefetch', async () => {
    batch.mockRejectedValueOnce(new ApiError('provider', 'The weather service returned an error.'))
    const { result } = renderHook(() => useAssessment())
    await act(async () => {
      await result.current.submit(VALID_REQUEST)
    })
    expect(result.current.state.phase).toBe('error')
    expect(result.current.data).toBeNull()
    expect(result.current.state.error?.message).toBe('The weather service returned an error.')

    batch.mockImplementation(async (r) => makeBatch(r))
    await act(async () => {
      result.current.retry()
    })
    expect(batch.mock.calls[1][0].departure_datetimes).toHaveLength(PREFETCH_OFFSETS.length)
    expect(result.current.state.phase).toBe('success')
  })

  it('an unexpected exception becomes a generic error with no internals', async () => {
    batch.mockRejectedValueOnce(new TypeError('x is not a function at C:/secret/file.ts'))
    const { result } = renderHook(() => useAssessment())
    await act(async () => {
      await result.current.submit(VALID_REQUEST)
    })
    expect(result.current.state.error?.message).not.toMatch(/secret|TypeError/)
  })

  it('refuses a response that answers for different departures than were asked', async () => {
    batch.mockImplementation(async (request: BatchRequest) => {
      const shifted = { ...request, departure_datetimes: request.departure_datetimes.map((d) => new Date(instant(d) + HOUR).toISOString()) }
      return makeBatch(shifted)
    })
    const { result } = renderHook(() => useAssessment())
    await act(async () => {
      await result.current.submit(VALID_REQUEST)
    })
    expect(result.current.data).toBeNull()
    expect(result.current.state.phase).toBe('error')
    expect(Object.values(result.current.state.entries).every((e) => e.kind === 'error')).toBe(true)
  })

  it('refuses a response with the wrong number of results', async () => {
    batch.mockImplementation(async (request: BatchRequest) => {
      const full = makeBatch(request)
      return { ...full, results: full.results.slice(0, 3) }
    })
    const { result } = renderHook(() => useAssessment())
    await act(async () => {
      await result.current.submit(VALID_REQUEST)
    })
    expect(result.current.state.phase).toBe('error')
    expect(result.current.data).toBeNull()
  })

  it('shows a failed departure as an error entry and keeps the others usable', async () => {
    batch.mockImplementation(async (request: BatchRequest) => makeBatch(request, (i) => (PREFETCH_OFFSETS[i] === 12 ? 'error' : 'recommended')))
    const { result } = renderHook(() => useAssessment())
    await act(async () => {
      await result.current.submit(VALID_REQUEST)
    })
    expect(result.current.state.entries[12].kind).toBe('error')
    expect(result.current.state.entries[18].kind).toBe('ok')
    expect(result.current.state.phase).toBe('success') // offset 0, the one requested for display, worked
  })

  it('re-requests an assessment that has become stale rather than showing it as current', async () => {
    const { result } = await submitted()
    const now = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(now + STALE_AFTER_MS + 1)
    await act(async () => {
      result.current.selectOffset(6)
    })
    expect(batch).toHaveBeenCalledTimes(2)
    expect(batch.mock.calls[1][0].departure_datetimes).toHaveLength(1)
  })

  it('treats an assessment just inside the freshness window as current', async () => {
    const { result } = await submitted()
    const fetchedAt = (result.current.state.entries[6] as { fetchedAt: number }).fetchedAt
    vi.spyOn(Date, 'now').mockReturnValue(fetchedAt + STALE_AFTER_MS)
    act(() => result.current.selectOffset(6))
    expect(batch).toHaveBeenCalledTimes(1)
  })
})
