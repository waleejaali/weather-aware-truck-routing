import type { RouteAssessment } from '../api/types'
import { sourceLabel } from '../lib/status'
import { compactDuration, formatLocalDateTime } from '../lib/time'
import { IconArrowRight, IconCheck, IconChevronDown, IconRoute } from './icons'
import { RiskDot, RiskMilesBar } from './RiskBadge'

interface Props {
  route: RouteAssessment
  selected: boolean
  isFastest: boolean
  onSelect: (id: string) => void
}

/** A compact comparison card: big distance and drive time, one risk line, details on demand. */
export function RouteCard({ route, selected, isFastest, onSelect }: Props) {
  const name = route.id.replace('route-', 'Route ')
  const s = route.risk_summary
  const lowCoverage = s.weather_coverage_percent < 80
  return (
    <article aria-label={`${name}, rank ${route.rank}`} className={`card flex flex-col p-5 ${selected ? 'border-accent' : ''}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-base font-semibold text-ink">
            <IconRoute size={16} className="shrink-0 text-muted" />
            {name}
            <span className="text-xs font-medium text-faint" aria-label={`Rank ${route.rank}`}>
              #{route.rank}
            </span>
          </h3>
          <p className="mt-1 text-sm text-muted">
            {sourceLabel(route.source)}
            {isFastest ? ' · Fastest' : ''}
          </p>
        </div>
        <span className="flex shrink-0 flex-col items-end gap-1.5">
          {route.recommended ? (
            <span className="rounded-md border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">★ Recommended</span>
          ) : null}
          {!route.eligible ? (
            <span className="rounded-md border border-line-strong bg-surface-2 px-2 py-0.5 text-xs font-semibold text-muted">Not eligible</span>
          ) : null}
        </span>
      </header>

      <dl className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <dd className="text-2xl font-bold tabular-nums text-ink">
            {route.distance_miles.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            <span className="ml-1 text-sm font-normal text-muted">mi</span>
          </dd>
          <dt className="mt-1 text-xs text-muted">Distance</dt>
        </div>
        <div>
          <dd className="text-2xl font-bold tabular-nums text-ink">{compactDuration(route.duration_seconds)}</dd>
          <dt className="mt-1 text-xs text-muted">Drive time</dt>
        </div>
      </dl>

      <div className="mt-6 flex items-center justify-between gap-3 border-t border-line pt-4">
        <span aria-label="Worst checkpoint risk">
          <RiskDot level={s.max_risk_level} suffix=" risk" />
        </span>
        <span className={`text-sm tabular-nums ${lowCoverage ? 'font-semibold text-red-300' : 'text-muted'}`}>
          {s.weather_coverage_percent.toFixed(0)}% coverage
        </span>
      </div>

      {!route.eligible && route.ineligible_reason ? (
        <p className="mt-3 rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-xs text-ink">
          <strong>Why not recommendable:</strong> {route.ineligible_reason}.
        </p>
      ) : null}

      <details className="group mt-3">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded text-xs font-medium text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
          Risk details
          <IconChevronDown size={14} className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-3 space-y-3">
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="eyebrow">Arrives</dt>
              <dd className="mt-0.5 text-sm font-semibold text-ink">{formatLocalDateTime(route.arrival_datetime)}</dd>
            </div>
            <div>
              <dt className="eyebrow">Avg risk score</dt>
              <dd className="mt-0.5 text-sm font-semibold tabular-nums text-ink">
                {s.average_score === null ? <span className="italic text-faint">No data</span> : `${s.average_score.toFixed(2)} / 4`}
              </dd>
            </div>
          </dl>
          <div>
            <p className="mb-2 text-xs font-medium text-muted">Estimated miles by risk level</p>
            <RiskMilesBar miles={s.miles} />
          </div>
          <p className="text-xs text-muted">
            <strong className="text-ink">Ranking:</strong> {route.ranking.explanation}
          </p>
        </div>
      </details>

      <button
        type="button"
        aria-pressed={selected}
        aria-label={selected ? `Showing ${name} on map` : `Show ${name} on map`}
        onClick={() => onSelect(route.id)}
        className="btn-ghost mt-5 w-full"
      >
        {selected ? (
          <>
            <IconCheck size={16} />
            Viewing on map
          </>
        ) : (
          <>
            View route
            <IconArrowRight size={16} />
          </>
        )}
      </button>
    </article>
  )
}
