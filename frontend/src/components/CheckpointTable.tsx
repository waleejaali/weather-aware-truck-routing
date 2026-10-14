import { useMemo, useState } from 'react'
import type { Checkpoint, RouteAssessment } from '../api/types'
import { formatLocalDateTime } from '../lib/time'
import { RiskBadge } from './RiskBadge'
import { Reading } from './shared'

interface Props {
  route: RouteAssessment
  windMetric: 'sustained' | 'gust'
  focusedIndex: number | null
  onFocus: (index: number) => void
}

const isProblem = (c: Checkpoint) =>
  c.weather_status !== 'complete' || (c.risk.combined !== null && c.risk.combined !== 'low')

function Cell({ children, level }: { children: React.ReactNode; level: Checkpoint['risk']['wind'] | undefined }) {
  return (
    <div className="space-y-0.5">
      <div>{children}</div>
      <RiskBadge level={level ?? null} size="xs" />
    </div>
  )
}

export function CheckpointTable({ route, windMetric, focusedIndex, onFocus }: Props) {
  const [onlyProblems, setOnlyProblems] = useState(false)
  const rows = useMemo(
    () => (onlyProblems ? route.checkpoints.filter(isProblem) : route.checkpoints),
    [route, onlyProblems],
  )
  const problemCount = useMemo(() => route.checkpoints.filter(isProblem).length, [route])
  const name = route.id.replace('route-', 'Route ')

  return (
    <section aria-label={`${name} checkpoints`} className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900">{name} checkpoints</h3>
          <p className="text-xs text-slate-600">
            {route.checkpoints.length} sampled points. Wind risk uses {windMetric === 'sustained' ? 'sustained wind' : 'wind gusts'}.
            Select a row to locate it on the map.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-800">
          <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="h-4 w-4" />
          Only above Low or missing data ({problemCount})
        </label>
      </header>

      <div className="max-h-[28rem] overflow-auto">
        <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
          <caption className="sr-only">Weather and risk at each checkpoint of {name}</caption>
          <thead className="sticky top-0 z-10 bg-slate-100 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" className="px-3 py-2">Mile</th>
              <th scope="col" className="px-3 py-2">ETA (local)</th>
              <th scope="col" className="px-3 py-2">Wind{windMetric === 'sustained' ? ' ✓ used' : ''}</th>
              <th scope="col" className="px-3 py-2">Gusts{windMetric === 'gust' ? ' ✓ used' : ''}</th>
              <th scope="col" className="px-3 py-2">Rain</th>
              <th scope="col" className="px-3 py-2">Snow</th>
              <th scope="col" className="px-3 py-2">Combined</th>
              <th scope="col" className="px-3 py-2">Weather data</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const w = c.weather
              const focused = focusedIndex === c.index
              return (
                <tr key={c.index} className={`border-t border-slate-200 align-top ${focused ? 'bg-indigo-50' : ''}`}>
                  <th scope="row" className="px-3 py-2 font-medium">
                    <button
                      type="button"
                      onClick={() => onFocus(c.index)}
                      aria-label={`Locate mile ${c.distance_miles} on map`}
                      className="rounded px-1 text-indigo-800 underline underline-offset-2 hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {c.distance_miles.toFixed(0)}
                    </button>
                  </th>
                  <td className="whitespace-nowrap px-3 py-2">{formatLocalDateTime(c.eta)}</td>
                  <td className="px-3 py-2">
                    <div><Reading value={w.wind_speed_mph} unit="mph" /></div>
                    {windMetric === 'sustained' ? <RiskBadge level={c.risk.wind} size="xs" /> : null}
                  </td>
                  <td className="px-3 py-2">
                    <div><Reading value={w.wind_gust_mph} unit="mph" /></div>
                    {windMetric === 'gust' ? <RiskBadge level={c.risk.wind} size="xs" /> : null}
                  </td>
                  <td className="px-3 py-2"><Cell level={c.risk.rain}><Reading value={w.rain_in_per_hr} unit="in/hr" digits={2} /></Cell></td>
                  <td className="px-3 py-2"><Cell level={c.risk.snow}><Reading value={w.snow_in_per_hr} unit="in/hr" digits={2} /></Cell></td>
                  <td className="px-3 py-2">
                    <RiskBadge level={c.risk.combined} />
                    {c.risk.load_override ? (
                      <p className="mt-1 text-xs text-slate-700">
                        Load rule: <RiskBadge level={c.risk.load_override} size="xs" />
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {c.weather_status === 'complete' ? (
                      <span className="text-slate-700">Complete</span>
                    ) : (
                      <>
                        <span className="font-semibold text-red-800">{c.weather_status === 'partial' ? 'Partial' : 'Unavailable'}</span>
                        <p className="mt-0.5 text-slate-700">{c.weather_missing_reason}</p>
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-slate-600">No checkpoints match this filter.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}
