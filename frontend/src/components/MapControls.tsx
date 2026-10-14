import type { ColorBy } from '../api/types'
import { ALL_RISK_META, RECOMMENDED_COLOR } from '../lib/risk'

const OPTIONS: { value: ColorBy; label: string }[] = [
  { value: 'combined', label: 'Combined risk' },
  { value: 'wind', label: 'Wind' },
  { value: 'rain', label: 'Rain' },
  { value: 'snow', label: 'Snow' },
]

export function ColorBySelector({ value, onChange }: { value: ColorBy; onChange: (v: ColorBy) => void }) {
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium text-slate-800">Colour the route corridor by</legend>
      <div className="flex flex-wrap gap-2" role="radiogroup">
        {OPTIONS.map((o) => (
          <label
            key={o.value}
            className={`cursor-pointer rounded-full border px-3 py-1 text-sm focus-within:ring-2 focus-within:ring-indigo-500 ${
              value === o.value ? 'border-indigo-700 bg-indigo-700 font-semibold text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
            }`}
          >
            <input type="radio" name="color-by" value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} className="sr-only" />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function MapLegend({ hasRecommendation }: { hasRecommendation: boolean }) {
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Risk colour legend">
        {ALL_RISK_META.map((m) => (
          <li key={m.key} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full border border-slate-900" style={{ background: m.color }} aria-hidden="true" />
            <span aria-hidden="true">{m.symbol}</span> {m.label}
            {m.key === 'unknown' ? ' (no weather data, dotted)' : ''}
          </li>
        ))}
      </ul>
      <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Route line legend">
        {hasRecommendation ? (
          <li className="flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-6 rounded" style={{ background: RECOMMENDED_COLOR }} aria-hidden="true" /> Blue = recommended route
          </li>
        ) : (
          <li>No route is recommended, so none is highlighted.</li>
        )}
        <li className="flex items-center gap-1.5">
          <span className="inline-block w-6 border-t-2 border-dashed border-slate-500" aria-hidden="true" /> Other candidate (click to select)
        </li>
      </ul>
      <p>
        Colours show the risk at each sampled checkpoint, applied to the road halfway to its neighbours. There is no
        interpolated weather between checkpoints.
      </p>
    </div>
  )
}
