import { useEffect, useMemo, useState } from 'react'
import type { CheckpointInterval, ColorBy } from './api/types'
import { AppHeader } from './components/AppHeader'
import { CheckpointsPage } from './components/CheckpointsPage'
import { ForecastSlider, type OffsetSummary } from './components/ForecastSlider'
import { IconSliders } from './components/icons'
import { PlannerForm } from './components/PlannerForm'
import { RecommendationBanner } from './components/RecommendationBanner'
import { RouteCard } from './components/RouteCard'
import { RouteOverview } from './components/RouteOverview'
import { EmptyState, ErrorPanel, LoadingState, MethodPanel } from './components/StatePanels'
import { isStale, statusOf, useAssessment } from './hooks/useAssessment'
import { useHashRoute } from './hooks/useHashRoute'
import { useNow } from './hooks/useNow'
import type { LatLng } from './lib/geo'
import { placeName, presetFor, type TripPreset } from './lib/presets'
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

const coordText = (lat: number, lon: number) => `${lat.toFixed(2)}, ${lon.toFixed(2)}`

function App() {
  const [page, navigate] = useHashRoute()
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

  // Each page starts at the top, and the tab title says where you are.
  useEffect(() => {
    window.scrollTo(0, 0)
    document.title = `${page === 'checkpoints' ? 'Checkpoints' : 'Route planner'} · Weather-Aware Routing`
  }, [page])

  // Coming back from the Checkpoints page to look at a point: bring the map into view.
  useEffect(() => {
    if (page === 'planner' && focus) document.getElementById('route-overview')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [page, focus])

  // A previous choice may not exist in a new result, so fall back to recommended, then first.
  const selectedId =
    data && chosenId && data.routes.some((r) => r.id === chosenId)
      ? chosenId
      : data
        ? (data.recommendation.recommended_route_id ?? data.routes[0]?.id ?? null)
        : null

  // Backend field errors (HTTP 400) shown on the matching inputs until the user edits them.
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

  const recommendedId = data?.recommendation.recommended_route_id ?? null
  const origin: LatLng | null = data ? [data.request.origin.latitude, data.request.origin.longitude] : null
  const destination: LatLng | null = data ? [data.request.destination.latitude, data.request.destination.longitude] : null
  const fitKey = data ? `${origin?.join(',')}>${destination?.join(',')}` : 'none'
  const routeError = error && error.kind !== 'validation' ? error : null
  const firstLoad = loading && !data
  const shownEntry = state.entries[state.shownOffset]
  const shownIsStale = shownEntry ? isStale(shownEntry, now) : false
  const fastest = data ? Math.min(...data.routes.map((r) => r.duration_seconds)) : 0

  // Label for the chip over the map: the assessed trip if there is one, else a recognised quick trip.
  const tripLabel = data
    ? {
        from: placeName(String(data.request.origin.latitude), String(data.request.origin.longitude)) ?? coordText(data.request.origin.latitude, data.request.origin.longitude),
        to: placeName(String(data.request.destination.latitude), String(data.request.destination.longitude)) ?? coordText(data.request.destination.latitude, data.request.destination.longitude),
      }
    : (() => {
        const preset = presetFor(values)
        return preset ? { from: preset.originName, to: preset.destName } : null
      })()

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

  const locate = (routeId: string, index: number) => {
    setChosenId(routeId)
    setFocus({ routeId, index })
    navigate('planner')
  }

  return (
    <div className="min-h-screen text-ink">
      <a href="#results" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to results
      </a>
      <AppHeader page={page} onNavigate={navigate} />

      <main className="mx-auto max-w-[96rem] px-4 pb-16 pt-10 sm:px-8">
        {page === 'checkpoints' ? (
          <CheckpointsPage
            data={data}
            selectedId={selectedId}
            onSelectRoute={setChosenId}
            focusedIndex={focus && focus.routeId === selectedId ? focus.index : null}
            onLocate={locate}
            onOpenPlanner={() => navigate('planner')}
          />
        ) : (
          <>
            <section className="mb-10 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">Plan a safer journey.</h1>
                <p className="mt-3 text-base text-muted">Compare routes by the weather ahead, not just the miles.</p>
              </div>
              <p className="flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm text-muted">
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-accent" />
                Live forecast · Open-Meteo
                {shownEntry?.kind === 'ok' ? ` · assessed ${new Date(shownEntry.fetchedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}
              </p>
            </section>

            <div className="grid gap-8 lg:grid-cols-[26rem_minmax(0,1fr)] lg:items-stretch">
              <section className="card overflow-hidden" aria-labelledby="trip-details-heading">
                <header className="flex items-center gap-3 border-b border-line px-6 py-5">
                  <IconSliders size={18} className="text-muted" />
                  <h2 id="trip-details-heading" className="text-lg font-semibold text-ink">
                    Trip details
                  </h2>
                </header>
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

              <RouteOverview
                routes={data?.routes ?? []}
                selectedId={selectedId}
                recommendedId={recommendedId}
                colorBy={colorBy}
                onColorBy={setColorBy}
                origin={origin}
                destination={destination}
                tripLabel={tripLabel}
                focus={focus}
                fitKey={fitKey}
                loading={loading}
                onSelectRoute={setChosenId}
                onCheckpointClick={(routeId, index) => setFocus({ routeId, index })}
              />
            </div>

            <div className="mt-10 space-y-10">
              {routeError ? <ErrorPanel error={routeError} onRetry={retry} /> : null}

              {data && shownIsStale ? (
                <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-400/50 bg-amber-400/10 p-4 text-sm text-amber-100">
                  <span>This assessment is more than 30 minutes old, so its forecast may have changed.</span>
                  <button
                    type="button"
                    onClick={() => selectOffset(state.shownOffset)}
                    className="rounded-lg bg-amber-400 px-3.5 py-1.5 text-xs font-bold text-slate-950 hover:bg-amber-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
                  >
                    Refresh
                  </button>
                </div>
              ) : null}

              {data ? <RecommendationBanner data={data} /> : null}

              <section id="results" tabIndex={-1} aria-labelledby="compare-heading" className="space-y-5 outline-none">
                <header className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 id="compare-heading" className="text-xl font-semibold text-ink">
                    Compare routes
                  </h2>
                  {data ? (
                    <p className="text-sm text-muted">
                      {data.routes.length} candidate route{data.routes.length === 1 ? '' : 's'}
                    </p>
                  ) : null}
                </header>
                {phase === 'idle' ? <EmptyState /> : null}
                {firstLoad ? <LoadingState message="Planning routes and fetching the forecast. This takes a few seconds…" /> : null}
                {data ? (
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    {data.routes.map((route) => (
                      <RouteCard
                        key={route.id}
                        route={route}
                        selected={route.id === selectedId}
                        isFastest={route.duration_seconds === fastest}
                        onSelect={setChosenId}
                      />
                    ))}
                  </div>
                ) : null}
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

              {data ? (
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <p className="text-sm text-muted">Need the full weather table for a route? Open the Checkpoints page for every sampled point.</p>
                  <a
                    href="#/checkpoints"
                    onClick={(e) => {
                      e.preventDefault()
                      navigate('checkpoints')
                    }}
                    className="btn-ghost"
                  >
                    View checkpoints
                  </a>
                </div>
              ) : null}
              {data ? <MethodPanel data={data} /> : null}
            </div>
          </>
        )}
      </main>

      <footer className="mx-auto max-w-[96rem] space-y-1.5 border-t border-line px-4 py-8 text-xs text-faint sm:px-8">
        <p>
          <a className="text-muted underline" href={data?.method.weather.attribution.url ?? 'https://open-meteo.com/'} target="_blank" rel="noreferrer">
            {data?.method.weather.attribution.text ?? 'Weather data by Open-Meteo.com'}
          </a>{' '}
          (
          <a className="text-muted underline" href={data?.method.weather.attribution.license_url ?? 'https://creativecommons.org/licenses/by/4.0/'} target="_blank" rel="noreferrer">
            {data?.method.weather.attribution.license ?? 'CC BY 4.0'}
          </a>
          ). Routing by OpenRouteService. Map tiles &copy; OpenStreetMap contributors.
        </p>
        <p>Weather-aware truck routing · Recommendations are based on forecast conditions at sampled checkpoints and are not a guarantee of safety.</p>
      </footer>
    </div>
  )
}

export default App
