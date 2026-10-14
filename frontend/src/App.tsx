import { useMemo, useState } from 'react'
import type { CheckpointInterval, ColorBy } from './api/types'
import { CheckpointTable } from './components/CheckpointTable'
import { ForecastSlider, type OffsetSummary } from './components/ForecastSlider'
import { ColorBySelector, MapLegend } from './components/MapControls'
import { MapView } from './components/MapView'
import { PlannerForm } from './components/PlannerForm'
import { RecommendationBanner } from './components/RecommendationBanner'
import { RouteCard } from './components/RouteCard'
import { EmptyState, ErrorPanel, LoadingState, MethodPanel } from './components/StatePanels'
import { isStale, statusOf, useAssessment } from './hooks/useAssessment'
import { useNow } from './hooks/useNow'
import type { LatLng } from './lib/geo'
import type { TripPreset } from './lib/presets'
import { defaultDepartureLocal, timeZoneLabel } from './lib/time'
import { mapServerFieldErrors, validateForm, type FormErrors, type FormField, type FormValues } from './lib/validation'

const FIELD_IDS: Record<FormField, string> = {
  originLat: 'origin-lat',
  originLon: 'origin-lon',
  destLat: 'dest-lat',
  destLon: 'dest-lon',
  departureLocal: 'departure',
  loadLb: 'load',
  interval: 'interval-error',
}

function initialValues(): FormValues {
  return {
    originLat: '',
    originLon: '',
    destLat: '',
    destLon: '',
    departureLocal: defaultDepartureLocal(),
    loadLb: '42000',
    interval: 25,
  }
}

function App() {
  const [values, setValues] = useState<FormValues>(initialValues)
  const [errors, setErrors] = useState<FormErrors>({})
  const [editedSinceError, setEditedSinceError] = useState<FormField[]>([])
  const [chosenId, setChosenId] = useState<string | null>(null)
  const [colorBy, setColorBy] = useState<ColorBy>('combined')
  const [focus, setFocus] = useState<{ routeId: string; index: number } | null>(null)
  const { state, data, submit, selectOffset, retry } = useAssessment()
  const { phase, error } = state
  const now = useNow()
  const loading = phase === 'loading'
  const tz = useMemo(() => timeZoneLabel(), [])

  // A previous choice may not exist in a new result, so fall back to recommended, then first.
  const selectedId =
    data && chosenId && data.routes.some((r) => r.id === chosenId)
      ? chosenId
      : data
        ? (data.recommendation.recommended_route_id ?? data.routes[0]?.id ?? null)
        : null

  const server = useMemo(
    () => (error?.kind === 'validation' && error.fields ? mapServerFieldErrors(error.fields) : { errors: {}, unmapped: [] as string[] }),
    [error],
  )
  const shownErrors: FormErrors = { ...errors }
  for (const [field, message] of Object.entries(server.errors) as [FormField, string][]) {
    if (!editedSinceError.includes(field)) shownErrors[field] = shownErrors[field] ?? message
  }

  const onChange = (field: FormField, value: string | CheckpointInterval) => {
    setValues((v) => ({ ...v, [field]: value }))
    setErrors((e) => (e[field] ? { ...e, [field]: undefined } : e))
    setEditedSinceError((list) => (list.includes(field) ? list : [...list, field]))
  }

  const onPreset = (preset: TripPreset) => {
    setValues((v) => ({ ...v, ...preset.values }))
    setErrors({})
  }

  const onSubmit = () => {
    const result = validateForm(values)
    if (!result.ok) {
      setErrors(result.errors)
      const first = (Object.keys(FIELD_IDS) as FormField[]).find((f) => result.errors[f])
      if (first) requestAnimationFrame(() => document.getElementById(FIELD_IDS[first])?.focus())
      return
    }
    setErrors({})
    setEditedSinceError([])
    setFocus(null)
    setChosenId(null)
    void submit(result.request)
  }

  const selected = data?.routes.find((r) => r.id === selectedId) ?? null
  const recommendedId = data?.recommendation.recommended_route_id ?? null
  const origin: LatLng | null = data ? [data.request.origin.latitude, data.request.origin.longitude] : null
  const destination: LatLng | null = data ? [data.request.destination.latitude, data.request.destination.longitude] : null
  const fitKey = data ? `${origin?.join(',')}>${destination?.join(',')}` : 'none'
  const routeError = error && error.kind !== 'validation' ? error : null
  const firstLoad = loading && !data
  const shownEntry = state.entries[state.shownOffset]
  const shownIsStale = shownEntry ? isStale(shownEntry, now) : false

  const summaries: OffsetSummary[] = Object.entries(state.entries)
    .map(([key, entry]): OffsetSummary => {
      const offsetHours = Number(key)
      if (entry.kind === 'error') return { offsetHours, state: 'error', message: entry.message }
      return {
        offsetHours,
        state: isStale(entry, now) ? 'stale' : 'ok',
        status: statusOf(entry) ?? undefined,
        recommendedRouteId: entry.data.recommendation.recommended_route_id,
        ageMinutes: Math.max(0, Math.round((now - entry.fetchedAt) / 60_000)),
      }
    })
    .sort((a, b) => a.offsetHours - b.offsetHours)

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <a href="#results" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to results
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[110rem] flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-4 sm:px-6">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Weather-Aware Truck Routing</h1>
          <p className="text-sm text-slate-600">Compare truck routes by forecast weather at the time you will be there.</p>
        </div>
      </header>

      <main className="mx-auto max-w-[110rem] px-4 py-6 sm:px-6">
        <div className="grid gap-6 lg:grid-cols-[26rem_minmax(0,1fr)] lg:items-start">
          <div className="space-y-4 lg:col-start-1 lg:row-start-1">
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold">Trip details</h2>
              <PlannerForm
                values={values}
                errors={shownErrors}
                generalError={error?.kind === 'validation' ? [error.message, ...server.unmapped].join(' ') : null}
                submitting={loading}
                timeZone={tz}
                onChange={onChange}
                onPreset={onPreset}
                onSubmit={onSubmit}
              />
            </section>
            {routeError ? <ErrorPanel error={routeError} onRetry={retry} /> : null}
            {data && shownIsStale ? (
              <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg border-l-4 border-amber-500 bg-amber-50 p-3 text-sm text-amber-950">
                <span>This assessment is more than 30 minutes old, so its forecast may have changed.</span>
                <button
                  type="button"
                  onClick={() => selectOffset(state.shownOffset)}
                  className="rounded-md bg-amber-700 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-800 focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  Refresh
                </button>
              </div>
            ) : null}
            {data ? <RecommendationBanner data={data} /> : null}
          </div>

          <div className="min-w-0 space-y-4 lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <section aria-label="Route map" className="space-y-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <ColorBySelector value={colorBy} onChange={setColorBy} />
              <div className="h-[26rem] sm:h-[32rem] lg:h-[36rem]">
                <MapView
                  routes={data?.routes ?? []}
                  selectedId={selectedId}
                  recommendedId={recommendedId}
                  colorBy={colorBy}
                  origin={origin}
                  destination={destination}
                  focus={focus}
                  fitKey={fitKey}
                  loading={loading}
                  onSelectRoute={setChosenId}
                  onCheckpointClick={(routeId, index) => setFocus({ routeId, index })}
                />
              </div>
              <MapLegend hasRecommendation={recommendedId !== null} />
            </section>
            {state.base && data ? (
              <ForecastSlider
                baseDeparture={state.base.departure_datetime}
                shownOffset={state.shownOffset}
                loading={loading}
                summaries={summaries}
                lastBatch={state.lastBatch}
                onCommit={(hours) => {
                  setFocus(null)
                  selectOffset(hours)
                }}
              />
            ) : null}
          </div>

          <div id="results" tabIndex={-1} className="space-y-4 lg:col-start-1 lg:row-start-2">
            {phase === 'idle' ? <EmptyState /> : null}
            {firstLoad ? <LoadingState message="Planning routes and fetching the forecast. This takes a few seconds…" /> : null}
            {data ? (
              <>
                <h2 className="text-lg font-semibold">
                  {data.routes.length} candidate route{data.routes.length === 1 ? '' : 's'}
                </h2>
                {data.routes.map((route) => (
                  <RouteCard key={route.id} route={route} selected={route.id === selectedId} onSelect={setChosenId} />
                ))}
                <MethodPanel data={data} />
              </>
            ) : null}
          </div>
        </div>

        {selected && data ? (
          <div className="mt-6">
            <CheckpointTable
              route={selected}
              windMetric={data.method.wind_metric}
              focusedIndex={focus?.routeId === selected.id ? focus.index : null}
              onFocus={(index) => setFocus({ routeId: selected.id, index })}
            />
          </div>
        ) : null}
      </main>

      <footer className="mx-auto max-w-[110rem] space-y-1 px-4 pb-8 text-xs text-slate-600 sm:px-6">
        <p>
          <a className="underline" href={data?.method.weather.attribution.url ?? 'https://open-meteo.com/'} target="_blank" rel="noreferrer">
            {data?.method.weather.attribution.text ?? 'Weather data by Open-Meteo.com'}
          </a>{' '}
          (
          <a className="underline" href={data?.method.weather.attribution.license_url ?? 'https://creativecommons.org/licenses/by/4.0/'} target="_blank" rel="noreferrer">
            {data?.method.weather.attribution.license ?? 'CC BY 4.0'}
          </a>
          ). Routing by OpenRouteService. Map tiles &copy; OpenStreetMap contributors.
        </p>
        <p>Recommendations are based on forecast conditions at sampled checkpoints and are not a guarantee of safety.</p>
      </footer>
    </div>
  )
}

export default App
