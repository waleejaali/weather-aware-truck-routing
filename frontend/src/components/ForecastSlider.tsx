import { useRef, useState } from 'react'
import type { RecommendationStatus } from '../api/types'
import type { BatchStats } from '../hooks/useAssessment'
import { statusInfo } from '../lib/status'
import { formatLocalDateTime, shiftIsoByHours } from '../lib/time'
import { IconClock, IconInfo } from './icons'

export const MAX_FORECAST_OFFSET_HOURS = 48
const COMMIT_DELAY_MS = 600
const TAB_OFFSETS = [0, 6, 12, 18, 24, 30, 36, 42, 48]

/** What is known about one departure offset, derived from the assessments held for this trip. */
export interface OffsetSummary {
  offsetHours: number
  state: 'ok' | 'stale' | 'error'
  status?: RecommendationStatus
  recommendedRouteId?: string | null
  /** Minutes since this offset was assessed (ok/stale). */
  ageMinutes?: number
  message?: string
}

interface Props {
  /** The departure the user submitted (offset 0). */
  baseDeparture: string
  /** Offset whose assessment is displayed. */
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

/** The second line of a departure tab: the recommended route, or why there isn't one. */
function tabSubtitle(s: OffsetSummary | undefined): string {
  if (!s) return 'Not assessed'
  if (s.state === 'error') return 'Failed - retry'
  const base = s.recommendedRouteId ? `${s.recommendedRouteId.replace('route-', 'Route ')}${s.status === 'recommended_incomplete_weather' ? ' (incomplete)' : ''}` : STATUS_SHORT[s.status!]
  return s.state === 'stale' ? `${base} · stale, refresh` : base
}

/**
 * "Explore departure times" (0-48 h after the entered departure). A bounded set of offsets is assessed together
 * when the trip is submitted (one server request, one route plan, one weather fetch). Other positions are
 * assessed on release, and old results are re-requested rather than shown as current. Weather is never
 * estimated in the browser.
 */
export function ForecastSlider({ baseDeparture, shownOffset, loading, summaries, lastBatch, onCommit }: Props) {
  const [pending, setPending] = useState(shownOffset)
  // When a different departure becomes the displayed one, follow it ("adjust state while rendering").
  const [seenShown, setSeenShown] = useState(shownOffset)
  if (shownOffset !== seenShown) {
    setSeenShown(shownOffset)
    setPending(shownOffset)
  }
  const timer = useRef<number | undefined>(undefined)

  const byOffset = new Map(summaries.map((s) => [s.offsetHours, s]))
  const usable = (offset: number) => byOffset.get(offset)?.state === 'ok'
  // The standard tabs plus any custom offset the user has assessed (for example +7 h).
  const offsets = [...new Set([...TAB_OFFSETS, ...summaries.map((s) => s.offsetHours)])].sort((a, b) => a - b)

  const change = (value: number, immediate = false) => {
    setPending(value)
    window.clearTimeout(timer.current)
    if (value === shownOffset && usable(value)) return
    // Already assessed and fresh: show it right away. Otherwise wait until the slider settles, then request it.
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
    <section aria-label="Forecast departure time" className="card p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <h2 className="flex items-center gap-2.5 text-base font-semibold text-ink">
          <IconClock size={18} className="text-muted" />
          Explore departure times
        </h2>
        <p className="text-sm text-muted" aria-live="polite">
          {pending === 0 ? 'Departing as entered' : `Departing +${pending} h`} · {formatLocalDateTime(departure)}
        </p>
      </div>

      <ul className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9">
        {offsets.map((h) => {
          const s = byOffset.get(h)
          const active = h === shownOffset
          return (
            <li key={h}>
              <button
                type="button"
                onClick={() => change(h, true)}
                aria-pressed={pending === h}
                aria-current={active ? 'true' : undefined}
                title={s?.status ? statusInfo(s.status).title : s?.message}
                className={`h-full w-full rounded-xl border px-2 py-3 text-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  active ? 'border-line-strong bg-surface-2' : 'border-transparent hover:bg-surface-2/60'
                } ${s?.state === 'error' ? 'border-red-400/50' : ''}`}
              >
                <span className={`block text-sm font-semibold ${active ? 'text-ink' : 'text-muted'}`}>{h === 0 ? 'As entered' : `+${h} h`}</span>
                <span className={`mt-1 block text-[11px] leading-tight ${active ? 'text-accent' : s?.state === 'error' ? 'text-red-300' : s?.state === 'stale' ? 'text-amber-300' : 'text-faint'}`}>
                  {tabSubtitle(s)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      <div className="relative mt-5">
        <input
          type="range"
          min={0}
          max={MAX_FORECAST_OFFSET_HOURS}
          step={1}
          value={pending}
          onChange={(e) => change(Number(e.target.value))}
          aria-label="Hours after the entered departure time"
          aria-valuetext={`${pending} hours after departure, ${formatLocalDateTime(departure)}`}
          className="w-full accent-accent"
        />
        {/* Marks show which departures actually have an assessment (filled), a stale one (amber) or a failure (outline). */}
        <div className="pointer-events-none relative mx-[7px] h-3" aria-hidden="true">
          {summaries.map((s) => (
            <span
              key={s.offsetHours}
              title={`+${s.offsetHours} h: ${s.state === 'error' ? 'failed' : s.state === 'stale' ? 'assessed, now stale' : 'assessed'}`}
              className={`absolute top-0 h-2.5 w-2.5 -translate-x-1/2 rounded-full border ${
                s.state === 'ok' ? 'border-accent bg-accent' : s.state === 'stale' ? 'border-amber-400 bg-amber-400' : 'border-red-400 bg-surface'
              }`}
              style={{ left: `${(s.offsetHours / MAX_FORECAST_OFFSET_HOURS) * 100}%` }}
            />
          ))}
        </div>
      </div>

      <p className="mt-3 text-sm text-ink" role="status">
        {hint}
      </p>
      <p className="mt-2 flex items-start gap-2 text-xs text-faint">
        <IconInfo size={14} className="mt-px shrink-0" />
        <span>
          Filled marks are departures assessed by the server with real forecast data; the weather is never estimated in your browser. Forecasts
          older than 30 minutes are refreshed, and departures beyond about 16 days ahead have no forecast.
          {lastBatch
            ? ` Last request: ${lastBatch.departures} departure${lastBatch.departures === 1 ? '' : 's'}, routes ${lastBatch.routeCache === 'hit' ? 'reused from the server cache' : 'planned once'}${
                lastBatch.routingRequests !== null && lastBatch.weatherRequests !== null
                  ? ` (${lastBatch.routingRequests} routing and ${lastBatch.weatherRequests} weather provider requests)`
                  : ''
              }.`
            : ''}
        </span>
      </p>
    </section>
  )
}
