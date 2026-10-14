import type { AssessResponse, RouteAssessment } from '../api/types'
import { statusInfo, type Tone } from '../lib/status'
import { formatLocalDateTime } from '../lib/time'

const TONES: Record<Tone, { box: string; icon: string; symbol: string }> = {
  success: { box: 'border-green-600 bg-green-50 text-green-950', icon: 'text-green-700', symbol: '✓' },
  caution: { box: 'border-amber-500 bg-amber-50 text-amber-950', icon: 'text-amber-700', symbol: '!' },
  danger: { box: 'border-red-600 bg-red-50 text-red-950', icon: 'text-red-700', symbol: '✕' },
  neutral: { box: 'border-slate-500 bg-slate-100 text-slate-900', icon: 'text-slate-700', symbol: '?' },
}

export function RecommendationBanner({ data }: { data: AssessResponse }) {
  const { recommendation, routes } = data
  const info = statusInfo(recommendation.status)
  const tone = TONES[info.tone]
  const recommended: RouteAssessment | undefined = routes.find((r) => r.id === recommendation.recommended_route_id)
  return (
    <section aria-label="Recommendation" className={`rounded-lg border-l-4 p-4 ${tone.box}`}>
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className={`mt-0.5 text-lg font-bold ${tone.icon}`}>
          {tone.symbol}
        </span>
        <div className="min-w-0 space-y-1">
          <h2 className="text-base font-semibold">{info.title}</h2>
          {recommended ? (
            <p className="text-sm font-medium">
              {recommended.id.replace('route-', 'Route ')}: {recommended.distance_miles.toLocaleString('en-US')} mi,{' '}
              {recommended.duration_text}, arriving {formatLocalDateTime(recommended.arrival_datetime)}
            </p>
          ) : null}
          <p className="text-sm">{recommendation.explanation}</p>
          {info.note ? <p className="text-xs opacity-80">{info.note}</p> : null}
          <p className="text-xs opacity-80">
            Departure {formatLocalDateTime(data.request.departure_datetime)} · Load{' '}
            {data.request.load_lb.toLocaleString('en-US')} lb
          </p>
        </div>
      </div>
    </section>
  )
}
