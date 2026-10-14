import { useRef, useState } from 'react'
import type { RecommendationStatus } from '../api/types'
import type { BatchStats } from '../hooks/useAssessment'
import { statusInfo } from '../lib/status'
import { formatLocalDateTime, shiftIsoByHours } from '../lib/time'

export const MAX_FORECAST_OFFSET_HOURS = 48
const COMMIT_DELAY_MS = 600
const QUICK_OFFSETS = [0, 6, 12, 18, 24, 30, 36, 42, 48]

export interface OffsetSummary {
  offsetHours: number
  state: 'ok' | 'stale' | 'error'
  status?: RecommendationStatus
  recommendedRouteId?: string | null
  ageMinutes?: number
  message?: string
}

interface Props {
  baseDeparture: string
  shownOffset: number
  loading: boolean
  summaries: OffsetSummary[]
  lastBatch: BatchStats | null
  onCommit: (offsetHours: number) => void
}

const STATUS_SHORT: Record<RecommendationStatus, string> = {
  recommended: 'Recommended',
  recommended_incomplete_weather: 'Recommended (incomplete)',
  no_safe_route: 'No safe route',
  insufficient_weather_data: 'Insufficient weather',
}

function ageText(minutes: number): string {
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  return `${Math.round(minutes / 60)} h ago`
}

export function ForecastSlider({ baseDeparture, shownOffset, loading, summaries, lastBatch, onCommit }: Props) {
  const [pending, setPending] = useState(shownOffset)
  // Sync to shownOffset during render instead of in an effect, to avoid a flash of the old value.
  const [seenShown, setSeenShown] = useState(shownOffset)
  if (shownOffset !== seenShown) {
    setSeenShown(shownOffset)
    setPending(shownOffset)
  }
  const timer = useRef<number | undefined>(undefined)

  const byOffset = new Map(summaries.map((s) => [s.offsetHours, s]))
  const usable = (offset: number) => byOffset.get(offset)?.state === 'ok'

  const change = (value: number, immediate = false) => {
    setPending(value)
    window.clearTimeout(timer.current)
    if (value === shownOffset && usable(value)) return
    // Debounce requests while dragging; fresh results can be shown immediately.
    if (immediate || usable(value)) onCommit(value)
    else timer.current = window.setTimeout(() => onCommit(value), COMMIT_DELAY_MS)
  }

  const departure = shiftIsoByHours(baseDeparture, pending)
  const here = byOffset.get(pending)
  let hint: string
  if (loading) hint = 'Assessing this departure…'
  else if (here?.state === 'ok') hint = `Assessed ${ageText(here.ageMinutes ?? 0)}.`
  else if (here?.state === 'stale') hint = `Assessed ${ageText(here.ageMinutes ?? 0)}, which is too old to show as current. Release to refresh.`
  else if (here?.state === 'error') hint = `This departure failed: ${here.message}. Release or select it to retry.`
  else hint = 'Not assessed yet. Release the slider to assess this departure.'

  return (
    <section aria-label="Forecast departure time" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">Forecast: depart later</h3>
        <p className="text-sm font-medium text-slate-900" aria-live="polite">
          {pending === 0 ? 'Departing as entered' : `Departing +${pending} h`}: {formatLocalDateTime(departure)}
        </p>
      </div>

      <div className="relative mt-3">
        <input
          type="range"
          min={0}
          max={MAX_FORECAST_OFFSET_HOURS}
          step={1}
          value={pending}
          onChange={(e) => change(Number(e.target.value))}
          aria-label="Hours after the entered departure time"
          aria-valuetext={`${pending} hours after departure, ${formatLocalDateTime(departure)}`}
          className="w-full accent-indigo-700"
        />
        <div className="pointer-events-none relative mx-[7px] h-3" aria-hidden="true">
          {summaries.map((s) => (
            <span
              key={s.offsetHours}
              title={`+${s.offsetHours} h: ${s.state === 'error' ? 'failed' : s.state === 'stale' ? 'assessed, now stale' : 'assessed'}`}
              className={`absolute top-0 h-2.5 w-2.5 -translate-x-1/2 rounded-full border text-[8px] leading-none ${
                s.state === 'ok' ? 'border-indigo-700 bg-indigo-700' : s.state === 'stale' ? 'border-amber-600 bg-amber-300' : 'border-red-700 bg-white'
              }`}
              style={{ left: `${(s.offsetHours / MAX_FORECAST_OFFSET_HOURS) * 100}%` }}
            />
          ))}
        </div>
      </div>
      <div className="flex justify-between text-[11px] text-slate-500" aria-hidden="true">
        <span>0 h</span>
        <span>12 h</span>
        <span>24 h</span>
        <span>36 h</span>
        <span>48 h</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {QUICK_OFFSETS.map((h) => (
          <button
            key={h}
            type="button"
            onClick={() => change(h, true)}
            aria-pressed={pending === h}
            className={`rounded-full border px-2.5 py-0.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              pending === h ? 'border-indigo-700 bg-indigo-700 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
            }`}
          >
            {h === 0 ? 'As entered' : `+${h} h`}
          </button>
        ))}
      </div>

      <p className="mt-3 text-xs text-slate-700" role="status">
        {hint}
      </p>
      <p className="mt-1 text-xs text-slate-600">
        Filled marks are departures assessed by the server with real forecast data; the weather is never estimated in your browser. Forecasts
        older than 30 minutes are refreshed, and departures beyond about 16 days ahead have no forecast.
        {lastBatch
          ? ` Last request: ${lastBatch.departures} departure${lastBatch.departures === 1 ? '' : 's'}, routes ${lastBatch.routeCache === 'hit' ? 'reused from the server cache' : 'planned once'}${
              lastBatch.routingRequests !== null && lastBatch.weatherRequests !== null
                ? ` (${lastBatch.routingRequests} routing and ${lastBatch.weatherRequests} weather provider requests)`
                : ''
            }.`
          : ''}
      </p>

      {summaries.length > 1 ? (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-slate-700">Departures assessed so far (select to view)</p>
          <ul className="flex flex-wrap gap-1.5">
            {summaries.map((v) => (
              <li key={v.offsetHours}>
                <button
                  type="button"
                  onClick={() => change(v.offsetHours, true)}
                  aria-current={v.offsetHours === shownOffset ? 'true' : undefined}
                  title={v.status ? statusInfo(v.status).title : v.message}
                  className={`rounded-md border px-2 py-1 text-left text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                    v.offsetHours === shownOffset ? 'border-indigo-700 bg-indigo-50' : 'border-slate-300 bg-white hover:bg-slate-100'
                  }`}
                >
                  <span className="font-semibold">{v.offsetHours === 0 ? 'As entered' : `+${v.offsetHours} h`}</span>
                  <br />
                  {v.state === 'error'
                    ? 'Failed - retry'
                    : `${STATUS_SHORT[v.status!]}${v.recommendedRouteId ? ` · ${v.recommendedRouteId.replace('route-', 'Route ')}` : ''}${v.state === 'stale' ? ' · stale, refresh' : ''}`}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
