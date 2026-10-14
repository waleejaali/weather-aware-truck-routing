import type { RouteAssessment } from '../api/types'
import { formatMiles } from '../lib/format'
import { sourceLabel } from '../lib/status'
import { formatLocalDateTime } from '../lib/time'
import { RiskBadge, RiskMilesBar } from './RiskBadge'

interface Props {
  route: RouteAssessment
  selected: boolean
  onSelect: (id: string) => void
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="text-sm font-medium text-slate-900">{children}</dd>
    </div>
  )
}

export function RouteCard({ route, selected, onSelect }: Props) {
  const name = route.id.replace('route-', 'Route ')
  const s = route.risk_summary
  return (
    <article
      aria-label={`${name}, rank ${route.rank}`}
      className={`rounded-lg border bg-white p-4 shadow-sm ${
        selected ? 'border-indigo-600 ring-2 ring-indigo-200' : 'border-slate-200'
      }`}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-sm font-bold text-white" aria-label={`Rank ${route.rank}`}>
          {route.rank}
        </span>
        <h3 className="text-base font-semibold text-slate-900">{name}</h3>
        <span className="text-xs text-slate-500">{sourceLabel(route.source)}</span>
        <span className="ml-auto flex flex-wrap gap-1.5">
          {route.recommended ? (
            <span className="rounded-full bg-blue-700 px-2 py-0.5 text-xs font-semibold text-white">★ Recommended</span>
          ) : null}
          {!route.eligible ? (
            <span className="rounded-full border border-slate-600 bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-800">
              Not eligible
            </span>
          ) : null}
        </span>
      </header>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <Stat label="Distance">{formatMiles(route.distance_miles, 0)}</Stat>
        <Stat label="Drive time">{route.duration_text}</Stat>
        <Stat label="Arrives">{formatLocalDateTime(route.arrival_datetime)}</Stat>
        <Stat label="Avg risk score">
          {s.average_score === null ? <span className="italic text-slate-500">No data</span> : `${s.average_score.toFixed(2)} / 4`}
        </Stat>
        <Stat label="Weather coverage">
          <span className={s.weather_coverage_percent < 80 ? 'text-red-800' : undefined}>{s.weather_coverage_percent.toFixed(0)}%</span>
        </Stat>
        <Stat label="Worst checkpoint">
          <RiskBadge level={s.max_risk_level} />
        </Stat>
      </dl>

      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-slate-600">Estimated miles by risk level</p>
        <RiskMilesBar miles={s.miles} />
      </div>

      {!route.eligible && route.ineligible_reason ? (
        <p className="mt-3 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-800">
          <strong>Why not recommendable:</strong> {route.ineligible_reason}.
        </p>
      ) : null}
      <p className="mt-2 text-xs text-slate-600">
        <strong>Ranking:</strong> {route.ranking.explanation}
      </p>

      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(route.id)}
        className={`mt-3 w-full rounded-md border px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
          selected ? 'border-indigo-700 bg-indigo-700 text-white' : 'border-slate-300 bg-white text-slate-800 hover:bg-slate-100'
        }`}
      >
        {selected ? `Showing ${name} on map` : `Show ${name} on map`}
      </button>
    </article>
  )
}
