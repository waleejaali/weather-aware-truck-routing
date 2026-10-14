import type { Checkpoint, RiskKey } from '../api/types'
import { confidentLevel, missingMeasurements } from '../lib/checkpoints'
import { formatLocalDateTime } from '../lib/time'
import { IconChevronRight } from './icons'
import { RiskDot } from './RiskBadge'
import { Reading } from './shared'

/** A reading plus its hazard level (omit `level` when no level is computed for it). "Low" stays quiet but is kept for screen readers. */
export function Hazard({ value, unit, digits, level }: { value: number | null; unit: string; digits?: number; level?: RiskKey | null }) {
  return (
    <div>
      <div className="font-medium text-ink">
        <Reading value={value} unit={unit} digits={digits} />
      </div>
      {level === undefined ? null : level === 'low' ? <span className="sr-only">Low</span> : <RiskDot level={level} size="xs" />}
    </div>
  )
}

interface Props {
  rows: Checkpoint[]
  routeName: string
  windMetric: 'sustained' | 'gust'
  focusedIndex: number | null
  onLocate: (index: number) => void
}

/** Desktop checkpoint table. Phones get CheckpointCards instead. */
export function CheckpointTable({ rows, routeName, windMetric, focusedIndex, onLocate }: Props) {
  const th = 'px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-faint'
  return (
    <div className="max-h-[40rem] overflow-auto">
      <table className="w-full min-w-[60rem] border-collapse text-left text-sm">
        <caption className="sr-only">Weather and risk at each checkpoint of {routeName}</caption>
        <thead className="sticky top-0 z-10 border-b border-line bg-surface-2">
          <tr>
            <th scope="col" className={th}>Mile</th>
            <th scope="col" className={th}>Estimated arrival</th>
            <th scope="col" className={th}>Wind{windMetric === 'sustained' ? ' · used' : ''}</th>
            <th scope="col" className={th}>Gusts{windMetric === 'gust' ? ' · used' : ''}</th>
            <th scope="col" className={th}>Rain</th>
            <th scope="col" className={th}>Snow</th>
            <th scope="col" className={th}>Combined risk</th>
            <th scope="col" className={th}>Weather data</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const w = c.weather
            const focused = focusedIndex === c.index
            return (
              <tr key={c.index} className={`border-t border-line align-top ${focused ? 'bg-accent/10' : ''}`}>
                <th scope="row" className="px-5 py-4 font-semibold">
                  <button
                    type="button"
                    onClick={() => onLocate(c.index)}
                    aria-label={`Locate mile ${c.distance_miles} on map`}
                    className="inline-flex items-center gap-1 rounded text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {c.distance_miles.toFixed(0)}
                    <IconChevronRight size={14} />
                  </button>
                </th>
                <td className="whitespace-nowrap px-5 py-4 text-muted">{formatLocalDateTime(c.eta)}</td>
                <td className="px-5 py-4"><Hazard value={w.wind_speed_mph} unit="mph" level={windMetric === 'sustained' ? c.risk.wind : undefined} /></td>
                <td className="px-5 py-4"><Hazard value={w.wind_gust_mph} unit="mph" level={windMetric === 'gust' ? c.risk.wind : undefined} /></td>
                <td className="px-5 py-4"><Hazard value={w.rain_in_per_hr} unit="in/hr" digits={2} level={c.risk.rain} /></td>
                <td className="px-5 py-4"><Hazard value={w.snow_in_per_hr} unit="in/hr" digits={2} level={c.risk.snow} /></td>
                <td className="px-5 py-4">
                  <RiskDot level={confidentLevel(c)} />
                  {missingMeasurements(c).length > 0 ? (
                    <p className="mt-0.5 text-xs font-medium text-amber-300">Not fully known: {missingMeasurements(c).join(', ')} missing</p>
                  ) : null}
                  {c.risk.load_override ? (
                    <p className="mt-1 text-xs text-muted">
                      Load rule: <RiskDot level={c.risk.load_override} size="xs" />
                    </p>
                  ) : null}
                </td>
                <td className="px-5 py-4 text-xs">
                  {c.weather_status === 'complete' ? (
                    <span className="text-muted">Complete</span>
                  ) : (
                    <>
                      <span className="font-semibold text-red-300">{c.weather_status === 'partial' ? 'Partial' : 'Unavailable'}</span>
                      <p className="mt-0.5 max-w-[16rem] text-muted">{c.weather_missing_reason}</p>
                    </>
                  )}
                </td>
              </tr>
            )
          })}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-5 py-10 text-center text-muted">
                No checkpoints match this filter.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}
