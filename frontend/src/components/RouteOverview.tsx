import type { ColorBy, RouteAssessment } from '../api/types'
import type { LatLng } from '../lib/geo'
import { IconArrowRight, IconLayers, IconTruck } from './icons'
import { ColorBySelector, MapLegend } from './MapControls'
import { MapView } from './MapView'

interface Props {
  routes: RouteAssessment[]
  selectedId: string | null
  recommendedId: string | null
  colorBy: ColorBy
  onColorBy: (value: ColorBy) => void
  origin: LatLng | null
  destination: LatLng | null
  /** Trip label shown over the map, e.g. "Chicago → Atlanta". */
  tripLabel: { from: string; to: string } | null
  focus: { routeId: string; index: number } | null
  fitKey: string
  loading: boolean
  onSelectRoute: (id: string) => void
  onCheckpointClick: (routeId: string, index: number) => void
}

/** The prominent map card: segmented risk selector, the map itself, and a compact legend. */
export function RouteOverview({ colorBy, onColorBy, tripLabel, recommendedId, ...map }: Props) {
  return (
    <section id="route-overview" aria-label="Route map" className="card flex flex-col overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
        <h2 className="flex items-center gap-2.5 text-base font-semibold text-ink">
          <IconLayers size={18} className="text-muted" />
          Route overview
        </h2>
        <ColorBySelector value={colorBy} onChange={onColorBy} />
      </header>

      <div className="relative min-h-[26rem] flex-1 sm:min-h-[34rem]">
        <div className="absolute inset-0">
          <MapView {...map} colorBy={colorBy} recommendedId={recommendedId} />
        </div>
        {tripLabel ? (
          <div className="pointer-events-none absolute left-4 top-4 z-[800] flex max-w-[calc(100%-6rem)] items-center gap-2.5 rounded-xl border border-line-strong bg-canvas/90 px-4 py-2.5 text-sm font-medium text-ink backdrop-blur">
            <IconTruck size={16} className="shrink-0 text-accent" />
            <span className="truncate">{tripLabel.from}</span>
            <IconArrowRight size={14} className="shrink-0 text-faint" />
            <span className="truncate">{tripLabel.to}</span>
          </div>
        ) : null}
      </div>

      <div className="border-t border-line px-6 py-4">
        <MapLegend hasRecommendation={recommendedId !== null} />
      </div>
    </section>
  )
}
