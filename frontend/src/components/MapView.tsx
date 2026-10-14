import type { CircleMarker as LeafletCircleMarker } from 'leaflet'
import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { Checkpoint, ColorBy, RouteAssessment } from '../api/types'
import { boundsOf, levelFor, riskSegments, toLatLng, type Bounds, type LatLng } from '../lib/geo'
import { RECOMMENDED_COLOR, riskMeta } from '../lib/risk'
import { formatLocalDateTime } from '../lib/time'
import { RiskBadge } from './RiskBadge'
import { Reading } from './shared'

const OTHER_ROUTE = '#64748b'

interface Props {
  routes: RouteAssessment[]
  selectedId: string | null
  /** null when the backend recommends nothing: then no route is highlighted as recommended. */
  recommendedId: string | null
  colorBy: ColorBy
  origin: LatLng | null
  destination: LatLng | null
  focus: { routeId: string; index: number } | null
  /** Changes when a different trip is loaded, so the map re-fits only then (not on every forecast step). */
  fitKey: string
  loading: boolean
  onSelectRoute: (id: string) => void
  onCheckpointClick: (routeId: string, index: number) => void
}

function FitBounds({ bounds, fitKey }: { bounds: Bounds | null; fitKey: string }) {
  const map = useMap()
  const lastKey = useRef('')
  useEffect(() => {
    if (bounds && fitKey !== lastKey.current) {
      lastKey.current = fitKey
      map.fitBounds(bounds, { padding: [32, 32] })
    }
  }, [bounds, fitKey, map])
  return null
}

function FocusCheckpoint({ markers, index }: { markers: RefObject<Map<number, LeafletCircleMarker>>; index: number | null }) {
  const map = useMap()
  useEffect(() => {
    if (index === null) return
    const marker = markers.current.get(index)
    if (marker) {
      map.panTo(marker.getLatLng())
      marker.openPopup()
    }
  }, [index, markers, map])
  return null
}

function CheckpointPopup({ route, checkpoint }: { route: RouteAssessment; checkpoint: Checkpoint }) {
  const w = checkpoint.weather
  const r = checkpoint.risk
  return (
    <div className="min-w-[14rem] space-y-1 text-sm">
      <p className="font-semibold">
        {route.id.replace('route-', 'Route ')} · mile {checkpoint.distance_miles.toFixed(0)}
      </p>
      <p>ETA {formatLocalDateTime(checkpoint.eta)}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <dt className="text-slate-600">Wind</dt>
        <dd><Reading value={w.wind_speed_mph} unit="mph" /> <RiskBadge level={r.wind} size="xs" /></dd>
        <dt className="text-slate-600">Gusts</dt>
        <dd><Reading value={w.wind_gust_mph} unit="mph" /></dd>
        <dt className="text-slate-600">Rain</dt>
        <dd><Reading value={w.rain_in_per_hr} unit="in/hr" digits={2} /> <RiskBadge level={r.rain} size="xs" /></dd>
        <dt className="text-slate-600">Snow</dt>
        <dd><Reading value={w.snow_in_per_hr} unit="in/hr" digits={2} /> <RiskBadge level={r.snow} size="xs" /></dd>
      </dl>
      <p>
        Combined: <RiskBadge level={r.combined} />
      </p>
      {r.load_override ? (
        <p>
          Load rule: <RiskBadge level={r.load_override} size="xs" />
        </p>
      ) : null}
      {checkpoint.weather_missing_reason ? (
        <p className="font-medium text-red-800">Missing data: {checkpoint.weather_missing_reason}</p>
      ) : null}
    </div>
  )
}

export function MapView({
  routes,
  selectedId,
  recommendedId,
  colorBy,
  origin,
  destination,
  focus,
  fitKey,
  loading,
  onSelectRoute,
  onCheckpointClick,
}: Props) {
  const markers = useRef(new Map<number, LeafletCircleMarker>())
  const paths = useMemo(() => new Map(routes.map((r) => [r.id, toLatLng(r.geometry.coordinates)])), [routes])
  const bounds = useMemo(() => boundsOf([...paths.values()]), [paths])
  const selected = routes.find((r) => r.id === selectedId) ?? null
  const segments = useMemo(() => (selected ? riskSegments(selected, colorBy) : []), [selected, colorBy])
  const others = routes.filter((r) => r.id !== selectedId)

  return (
    <div className="relative h-full min-h-[22rem] w-full overflow-hidden rounded-lg border border-slate-300 bg-slate-200">
      <MapContainer
        center={[39.5, -98.35]}
        zoom={4}
        preferCanvas
        scrollWheelZoom
        className="h-full w-full"
        aria-label="Map of candidate truck routes"
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />
        <FitBounds bounds={bounds} fitKey={fitKey} />

        {/* Routes that are not selected: thin grey lines, with the recommended one picked out in blue. */}
        {others.map((route) => {
          const isRecommended = route.id === recommendedId
          const positions = paths.get(route.id)!
          return (
            <Polyline
              key={route.id}
              positions={positions}
              pathOptions={{
                color: isRecommended ? RECOMMENDED_COLOR : OTHER_ROUTE,
                weight: isRecommended ? 6 : 4,
                opacity: isRecommended ? 0.9 : 0.65,
                dashArray: isRecommended ? undefined : '8 6',
              }}
              eventHandlers={{ click: () => onSelectRoute(route.id) }}
            >
              <Tooltip sticky>
                {route.id.replace('route-', 'Route ')} · {route.distance_miles.toFixed(0)} mi · {route.duration_text}
                {isRecommended ? ' · recommended' : ''} (click to select)
              </Tooltip>
            </Polyline>
          )
        })}

        {/* Selected route: halo (blue only if it is the recommended route), white casing, then the risk corridor. */}
        {selected ? (
          <>
            {selected.id === recommendedId ? (
              <Polyline positions={paths.get(selected.id)!} pathOptions={{ color: RECOMMENDED_COLOR, weight: 16, opacity: 0.85 }} interactive={false} />
            ) : null}
            <Polyline positions={paths.get(selected.id)!} pathOptions={{ color: '#ffffff', weight: 10, opacity: 1 }} interactive={false} />
            {segments.map((segment) => {
              const meta = riskMeta(segment.level)
              return (
                <Polyline
                  key={segment.checkpointIndex}
                  positions={segment.positions}
                  pathOptions={{
                    color: meta.color,
                    weight: 6,
                    opacity: 1,
                    dashArray: segment.level === null ? '2 8' : undefined,
                    lineCap: 'butt',
                  }}
                  interactive={false}
                />
              )
            })}
            {selected.checkpoints.map((checkpoint) => {
              const level = levelFor(checkpoint, colorBy)
              const meta = riskMeta(level)
              const focused = focus?.routeId === selected.id && focus.index === checkpoint.index
              return (
                <CircleMarker
                  key={checkpoint.index}
                  ref={(marker) => {
                    if (marker) markers.current.set(checkpoint.index, marker)
                    else markers.current.delete(checkpoint.index)
                  }}
                  center={[checkpoint.latitude, checkpoint.longitude]}
                  radius={focused ? 10 : 6}
                  pathOptions={{ color: '#0f172a', weight: focused ? 3 : 1.5, fillColor: meta.color, fillOpacity: 1 }}
                  eventHandlers={{ click: () => onCheckpointClick(selected.id, checkpoint.index) }}
                >
                  <Popup>
                    <CheckpointPopup route={selected} checkpoint={checkpoint} />
                  </Popup>
                </CircleMarker>
              )
            })}
            <FocusCheckpoint markers={markers} index={focus?.routeId === selected.id ? focus.index : null} />
          </>
        ) : null}

        {origin ? (
          <CircleMarker center={origin} radius={8} pathOptions={{ color: '#0f172a', weight: 3, fillColor: '#ffffff', fillOpacity: 1 }}>
            <Tooltip permanent direction="top" offset={[0, -8]}>Origin</Tooltip>
          </CircleMarker>
        ) : null}
        {destination ? (
          <CircleMarker center={destination} radius={8} pathOptions={{ color: '#0f172a', weight: 3, fillColor: '#0f172a', fillOpacity: 1 }}>
            <Tooltip permanent direction="top" offset={[0, -8]}>Destination</Tooltip>
          </CircleMarker>
        ) : null}
      </MapContainer>

      {loading ? (
        <div className="pointer-events-none absolute inset-0 z-[1000] flex items-start justify-center bg-white/50 pt-6">
          <p role="status" className="rounded-full bg-slate-900 px-4 py-1.5 text-sm font-medium text-white shadow">
            Assessing routes and weather…
          </p>
        </div>
      ) : null}
    </div>
  )
}
