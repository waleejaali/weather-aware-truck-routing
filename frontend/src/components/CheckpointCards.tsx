import type { Checkpoint } from '../api/types'
import { confidentLevel, missingMeasurements } from '../lib/checkpoints'
import { formatLocalDateTime } from '../lib/time'
import { Hazard } from './CheckpointTable'
import { IconChevronRight } from './icons'
import { RiskDot } from './RiskBadge'

interface Props {
  rows: Checkpoint[]
  windMetric: 'sustained' | 'gust'
  focusedIndex: number | null
  onLocate: (index: number) => void
}

/** Phone layout for checkpoints: one card per point instead of a wide table. */
export function CheckpointCards({ rows, windMetric, focusedIndex, onLocate }: Props) {
  if (rows.length === 0) return <p className="px-5 py-10 text-center text-sm text-muted">No checkpoints match this filter.</p>
  return (
    <ul className="divide-y divide-line">
      {rows.map((c) => {
        const w = c.weather
        return (
          <li key={c.index} className={`space-y-4 px-5 py-4 ${focusedIndex === c.index ? 'bg-accent/10' : ''}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <button
                  type="button"
                  onClick={() => onLocate(c.index)}
                  aria-label={`Locate mile ${c.distance_miles} on map`}
                  className="inline-flex items-center gap-1 rounded text-base font-bold text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  Mile {c.distance_miles.toFixed(0)}
                  <IconChevronRight size={14} />
                </button>
                <p className="mt-0.5 text-xs text-muted">{formatLocalDateTime(c.eta)}</p>
              </div>
              <div className="text-right">
                <p className="eyebrow">Combined</p>
                <RiskDot level={confidentLevel(c)} />
                  {missingMeasurements(c).length > 0 ? (
                    <p className="mt-0.5 text-xs font-medium text-amber-300">Not fully known: {missingMeasurements(c).join(', ')} missing</p>
                  ) : null}
                {c.risk.load_override ? (
                  <p className="mt-1 text-xs text-muted">
                    Load rule: <RiskDot level={c.risk.load_override} size="xs" />
                  </p>
                ) : null}
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <div>
                <dt className="eyebrow">Wind{windMetric === 'sustained' ? ' · used' : ''}</dt>
                <dd className="mt-1"><Hazard value={w.wind_speed_mph} unit="mph" level={windMetric === 'sustained' ? c.risk.wind : undefined} /></dd>
              </div>
              <div>
                <dt className="eyebrow">Gusts{windMetric === 'gust' ? ' · used' : ''}</dt>
                <dd className="mt-1"><Hazard value={w.wind_gust_mph} unit="mph" level={windMetric === 'gust' ? c.risk.wind : undefined} /></dd>
              </div>
              <div>
                <dt className="eyebrow">Rain</dt>
                <dd className="mt-1"><Hazard value={w.rain_in_per_hr} unit="in/hr" digits={2} level={c.risk.rain} /></dd>
              </div>
              <div>
                <dt className="eyebrow">Snow</dt>
                <dd className="mt-1"><Hazard value={w.snow_in_per_hr} unit="in/hr" digits={2} level={c.risk.snow} /></dd>
              </div>
            </dl>
            {c.weather_status !== 'complete' ? (
              <p className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-xs text-red-100">
                <strong>{c.weather_status === 'partial' ? 'Partial data' : 'Weather unavailable'}:</strong> {c.weather_missing_reason}
              </p>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
