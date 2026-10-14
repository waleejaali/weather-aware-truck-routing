import type { ApiError } from '../api/routes'
import type { AssessResponse } from '../api/types'
import { IconAlert, IconChevronDown, IconRoute } from './icons'

/** Shown in the "Compare routes" area before any assessment. */
export function EmptyState() {
  return (
    <section aria-label="Getting started" className="rounded-2xl border border-dashed border-line-strong px-6 py-10 text-center">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-accent">
        <IconRoute size={22} />
      </span>
      <h3 className="mt-4 text-lg font-semibold text-ink">Your route comparison will appear here</h3>
      <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
        Enter a trip and choose <strong className="text-ink">Assess routes</strong>. The app finds up to three truck routes, checks the
        forecast at each checkpoint for when the truck is expected to be there, and ranks the routes by weather risk.
      </p>
    </section>
  )
}

export function LoadingState({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" aria-label="Loading results" className="space-y-4">
      <p className="text-sm font-medium text-muted">{message}</p>
      <div className="grid gap-5 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-56 animate-pulse rounded-2xl border border-line bg-surface" />
        ))}
      </div>
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
    <div role="alert" className="flex gap-4 rounded-2xl border border-red-400/50 bg-red-500/10 p-5 sm:p-6">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-500/15 text-red-300">
        <IconAlert size={20} />
      </span>
      <div className="min-w-0 flex-1 text-red-100">
        <h2 className="text-base font-semibold">{TITLES[error.kind]}</h2>
        <p className="mt-1 text-sm">{error.message}</p>
        {error.kind === 'validation' ? <p className="mt-1 text-sm">Fix the highlighted fields and assess again.</p> : null}
        {unmapped && unmapped.length > 0 ? (
          <ul className="mt-1 list-disc pl-5 text-sm">
            {unmapped.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        ) : null}
        {error.kind === 'no_route' ? <p className="mt-1 text-sm">Check that both points are on or near drivable roads.</p> : null}
        {error.retryable && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-300"
          >
            Try again
          </button>
        ) : null}
      </div>
    </div>
  )
}

/** Assumptions, sampling and provider notes that must accompany any recommendation. */
export function MethodPanel({ data }: { data: AssessResponse }) {
  const { method } = data
  const notes = [...method.routing.notes, ...method.notes]
  return (
    <details className="card group p-5 text-sm sm:px-6">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1">
          How this was calculated · {method.checkpoint_interval_miles}-mile checkpoints · {method.wind_metric === 'sustained' ? 'sustained wind' : 'wind gusts'} · {method.min_weather_coverage_percent}% minimum coverage
        </span>
        <IconChevronDown size={18} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-4 space-y-4 text-muted">
        <ul className="list-disc space-y-1.5 pl-5">
          {method.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
        <p>
          Routing: {method.routing.provider} ({method.routing.profile}), {method.routing.returned_routes} of {method.routing.requested_routes} routes found (
          {method.routing.status}).
        </p>
        {notes.length > 0 ? (
          <div>
            <p className="font-medium text-ink">Notes</p>
            <ul className="mt-1 list-disc space-y-1.5 pl-5">
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
