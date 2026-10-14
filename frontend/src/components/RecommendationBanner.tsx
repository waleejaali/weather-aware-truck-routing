import type { AssessResponse, RouteAssessment } from '../api/types'
import { statusInfo, type Tone } from '../lib/status'
import { formatDuration, formatLocalDateTime } from '../lib/time'
import { IconAlert, IconCheck, IconClock, IconInfo, IconX } from './icons'

const TONES: Record<Tone, { box: string; icon: string; Glyph: typeof IconCheck }> = {
  success: { box: 'border-emerald-400/40', icon: 'bg-emerald-400/15 text-emerald-300', Glyph: IconCheck },
  caution: { box: 'border-amber-400/50', icon: 'bg-amber-400/15 text-amber-300', Glyph: IconAlert },
  danger: { box: 'border-red-400/50', icon: 'bg-red-500/15 text-red-300', Glyph: IconX },
  neutral: { box: 'border-line-strong', icon: 'bg-surface-2 text-muted', Glyph: IconInfo },
}

/** How the recommended route compares on time with the fastest candidate, computed from the returned routes. */
function timeTradeoff(recommended: RouteAssessment, routes: RouteAssessment[]): string {
  const fastest = Math.min(...routes.map((r) => r.duration_seconds))
  const extra = recommended.duration_seconds - fastest
  return extra <= 0 ? 'Fastest route' : `+${formatDuration(extra)} vs fastest`
}

export function RecommendationBanner({ data }: { data: AssessResponse }) {
  const { recommendation, routes } = data
  const info = statusInfo(recommendation.status)
  const tone = TONES[info.tone]
  const recommended: RouteAssessment | undefined = routes.find((r) => r.id === recommendation.recommended_route_id)
  const name = recommended?.id.replace('route-', 'Route ')
  const title = recommended
    ? `${name} is recommended${recommendation.status === 'recommended_incomplete_weather' ? ', but weather data is incomplete' : ''}`
    : info.title

  return (
    <section aria-label="Recommendation" className={`card flex flex-wrap items-start gap-x-5 gap-y-3 border p-5 sm:p-6 ${tone.box}`}>
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone.icon}`}>
        <tone.Glyph size={20} />
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {recommended ? (
          <p className="text-sm font-medium text-ink">
            {recommended.distance_miles.toLocaleString('en-US')} mi · {recommended.duration_text} · arrives {formatLocalDateTime(recommended.arrival_datetime)}
          </p>
        ) : null}
        <p className="text-sm text-muted">{recommendation.explanation}</p>
        {info.note ? <p className="text-sm text-muted">{info.note}</p> : null}
        <p className="text-xs text-faint">
          Departure {formatLocalDateTime(data.request.departure_datetime)} · Load {data.request.load_lb.toLocaleString('en-US')} lb
        </p>
      </div>
      {recommended ? (
        <span className="flex w-full items-center justify-center gap-2 rounded-full border border-line-strong px-3.5 py-1.5 text-sm font-semibold text-accent sm:w-auto sm:justify-start">
          <IconClock size={16} />
          {timeTradeoff(recommended, routes)}
        </span>
      ) : null}
    </section>
  )
}
