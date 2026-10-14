import type { ColorBy } from '../api/types'
import { ALL_RISK_META, RECOMMENDED_COLOR } from '../lib/risk'

const OPTIONS: { value: ColorBy; label: string }[] = [
  { value: 'combined', label: 'Combined risk' },
  { value: 'wind', label: 'Wind' },
  { value: 'rain', label: 'Rain' },
  { value: 'snow', label: 'Snow' },
]

/** Which hazard colours the route corridor and checkpoint markers. */
export function ColorBySelector({ value, onChange }: { value: ColorBy; onChange: (v: ColorBy) => void }) {
  return (
    <div role="radiogroup" aria-label="Colour the route corridor by" className="seg">
      {OPTIONS.map((o) => (
        <label key={o.value} data-checked={value === o.value}>
          <input type="radio" name="color-by" value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} className="sr-only" />
          {o.label}
        </label>
      ))}
    </div>
  )
}

export function MapLegend({ hasRecommendation }: { hasRecommendation: boolean }) {
  return (
    <div className="space-y-2.5 text-xs text-muted">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-2">
        <ul className="flex flex-wrap gap-x-5 gap-y-1.5" aria-label="Risk colour legend">
          {ALL_RISK_META.map((m) => (
            <li key={m.key} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: m.color }} aria-hidden="true" />
              <span aria-hidden="true" style={{ color: m.color }}>
                {m.symbol}
              </span>
              {m.key === 'unknown' ? 'Unknown (no data, dotted)' : m.label}
            </li>
          ))}
        </ul>
        <ul className="flex flex-wrap gap-x-5 gap-y-1.5" aria-label="Route line legend">
          {hasRecommendation ? (
            <li className="flex items-center gap-2">
              <span className="inline-block h-1 w-6 rounded" style={{ background: RECOMMENDED_COLOR }} aria-hidden="true" /> Blue = recommended route
            </li>
          ) : (
            <li>No route is recommended, so none is highlighted.</li>
          )}
          <li className="flex items-center gap-2">
            <span className="inline-block w-6 border-t-2 border-dashed border-line-strong" aria-hidden="true" /> Other candidate (click to select)
          </li>
        </ul>
      </div>
      <p className="text-faint">
        Colours show the risk at each sampled checkpoint, applied to the road halfway to its neighbours. There is no interpolated weather
        between checkpoints.
      </p>
    </div>
  )
}
