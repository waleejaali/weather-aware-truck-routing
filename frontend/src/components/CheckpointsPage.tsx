import { useMemo, useState } from 'react'
import type { AssessResponse } from '../api/types'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { isProblem } from '../lib/checkpoints'
import { checkpointsToCsv, csvFilename, downloadCsv } from '../lib/csv'
import { formatLocalDateTime } from '../lib/time'
import { CheckpointCards } from './CheckpointCards'
import { CheckpointTable } from './CheckpointTable'
import { IconArrowRight, IconDownload } from './icons'

interface Props {
  data: AssessResponse | null
  selectedId: string | null
  onSelectRoute: (id: string) => void
  focusedIndex: number | null
  /** Show a checkpoint on the planner's map. */
  onLocate: (routeId: string, index: number) => void
  onOpenPlanner: () => void
}

export function CheckpointsPage({ data, selectedId, onSelectRoute, focusedIndex, onLocate, onOpenPlanner }: Props) {
  const [onlyProblems, setOnlyProblems] = useState(false)
  const wide = useMediaQuery('(min-width: 768px)')
  const route = data ? (data.routes.find((r) => r.id === selectedId) ?? data.routes[0] ?? null) : null
  const rows = useMemo(() => (route ? (onlyProblems ? route.checkpoints.filter(isProblem) : route.checkpoints) : []), [route, onlyProblems])
  const problemCount = useMemo(() => (route ? route.checkpoints.filter(isProblem).length : 0), [route])

  if (!data || !route) {
    return (
      <section aria-label="No checkpoints yet" className="mx-auto max-w-2xl rounded-2xl border border-dashed border-line-strong px-6 py-14 text-center">
        <h1 className="text-2xl font-bold text-ink">No checkpoints yet</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">
          Checkpoints appear here after you assess a trip: the estimated arrival, weather and risk at every sampled point along each route.
        </p>
        <button type="button" onClick={onOpenPlanner} className="btn-primary mt-6">
          Plan a trip
          <IconArrowRight size={18} />
        </button>
      </section>
    )
  }

  const name = route.id.replace('route-', 'Route ')
  const windMetric = data.method.wind_metric
  const exportCsv = () => downloadCsv(csvFilename(route), checkpointsToCsv(route))

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div>
          <p className="eyebrow">Checkpoints</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">{name} checkpoints</h1>
          <p className="mt-2 text-sm text-muted">{route.checkpoints.length} sampled points · Estimated arrival and weather conditions</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="h-4 w-4 accent-accent" />
            Above low risk only ({problemCount})
          </label>
          <button type="button" onClick={exportCsv} className="btn-ghost">
            <IconDownload size={16} />
            Export
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
        <div role="radiogroup" aria-label="Route" className="seg">
          {data.routes.map((r) => (
            <label key={r.id} data-checked={r.id === route.id}>
              <input type="radio" name="checkpoint-route" value={r.id} checked={r.id === route.id} onChange={() => onSelectRoute(r.id)} className="sr-only" />
              {r.id.replace('route-', 'Route ')}
              {r.recommended ? ' ★' : ''}
            </label>
          ))}
        </div>
        <p className="text-sm text-muted">
          Departure {formatLocalDateTime(route.departure_datetime)} · Load {data.request.load_lb.toLocaleString('en-US')} lb · every{' '}
          {data.method.checkpoint_interval_miles} mi · wind risk uses {windMetric === 'sustained' ? 'sustained wind' : 'wind gusts'}
        </p>
      </div>

      <section aria-label={`${name} checkpoints`} className="card overflow-hidden">
        {wide ? (
          <CheckpointTable rows={rows} routeName={name} windMetric={windMetric} focusedIndex={focusedIndex} onLocate={(i) => onLocate(route.id, i)} />
        ) : (
          <CheckpointCards rows={rows} windMetric={windMetric} focusedIndex={focusedIndex} onLocate={(i) => onLocate(route.id, i)} />
        )}
      </section>
      <p className="text-xs text-faint">
        Select a mile marker to see that checkpoint on the map. Risk is sampled at these points and applied to the road halfway to the
        neighbouring checkpoints; hazards between checkpoints can be missed. Missing weather is shown as "No data", never as zero.
      </p>
    </div>
  )
}
