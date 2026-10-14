import type { ApiError } from '../api/routes'
import type { AssessResponse } from '../api/types'

export function EmptyState() {
  return (
    <section aria-label="Getting started" className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center">
      <h2 className="text-lg font-semibold text-slate-900">Plan a weather-aware route</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">
        Enter an origin, destination, departure time and load weight, then choose <strong>Assess Routes</strong>. The app
        finds up to three truck routes, checks the forecast at each checkpoint when the truck is expected to be there, and
        ranks the routes by weather risk.
      </p>
      <ol className="mx-auto mt-4 max-w-sm list-decimal space-y-1 pl-5 text-left text-sm text-slate-700">
        <li>Fill in the trip (or use a quick-fill trip).</li>
        <li>Compare routes, risk miles and checkpoints.</li>
        <li>Use the forecast slider to see how a later departure changes the weather.</li>
      </ol>
    </section>
  )
}

export function LoadingState({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3" aria-label="Loading results">
      <p className="text-sm font-medium text-slate-800">{message}</p>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-40 animate-pulse rounded-lg bg-slate-200" />
      ))}
    </div>
  )
}

const TITLES: Record<ApiError['kind'], string> = {
  validation: 'The server rejected the request',
  no_route: 'No drivable route found',
  provider: 'A routing or weather service is unavailable',
  server: 'The server hit an error',
  network: 'Could not reach the server',
  timeout: 'The request timed out',
  unexpected: 'Unexpected response',
  cancelled: 'Request cancelled',
}

export function ErrorPanel({ error, unmapped, onRetry }: { error: ApiError; unmapped?: string[]; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border-l-4 border-red-600 bg-red-50 p-4 text-red-950">
      <h2 className="text-base font-semibold">{TITLES[error.kind]}</h2>
      <p className="mt-1 text-sm">{error.message}</p>
      {error.kind === 'validation' ? (
        <p className="mt-1 text-sm">Fix the highlighted fields and assess again.</p>
      ) : null}
      {unmapped && unmapped.length > 0 ? (
        <ul className="mt-1 list-disc pl-5 text-sm">
          {unmapped.map((u) => (
            <li key={u}>{u}</li>
          ))}
        </ul>
      ) : null}
      {error.kind === 'no_route' ? (
        <p className="mt-1 text-sm">Check that both points are on or near drivable roads.</p>
      ) : null}
      {error.retryable && onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-800 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
        >
          Try again
        </button>
      ) : null}
    </div>
  )
}

export function MethodPanel({ data }: { data: AssessResponse }) {
  const { method } = data
  const notes = [...method.routing.notes, ...method.notes]
  return (
    <details className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <summary className="cursor-pointer font-semibold text-slate-900">
        How this was calculated · {method.checkpoint_interval_miles}-mile checkpoints · {method.wind_metric === 'sustained' ? 'sustained wind' : 'wind gusts'} · {method.min_weather_coverage_percent}% minimum coverage
      </summary>
      <div className="mt-3 space-y-3 text-slate-700">
        <ul className="list-disc space-y-1 pl-5">
          {method.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
        <p>
          Routing: {method.routing.provider} ({method.routing.profile}), {method.routing.returned_routes} of{' '}
          {method.routing.requested_routes} routes found ({method.routing.status}).
        </p>
        {notes.length > 0 ? (
          <div>
            <p className="font-medium text-slate-900">Notes</p>
            <ul className="list-disc space-y-1 pl-5">
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  )
}
