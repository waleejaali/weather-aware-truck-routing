import type { RouteAssessment } from '../api/types'

const HEADER = [
  'route', 'mile', 'eta_utc', 'latitude', 'longitude', 'wind_mph', 'gust_mph', 'rain_in_per_hr', 'snow_in_per_hr',
  'wind_used_mph', 'wind_risk', 'rain_risk', 'snow_risk', 'combined_risk', 'load_rule', 'weather_status', 'missing_reason',
]

function cell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '' // missing stays empty: never a 0 standing in for no data
  const text = String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** CSV of one route's checkpoints exactly as returned by the API (units are in the column names). */
export function checkpointsToCsv(route: RouteAssessment): string {
  const rows = route.checkpoints.map((c) =>
    [
      route.id, c.distance_miles, c.eta, c.latitude, c.longitude, c.weather.wind_speed_mph, c.weather.wind_gust_mph,
      c.weather.rain_in_per_hr, c.weather.snow_in_per_hr, c.weather.wind_used_mph, c.risk.wind, c.risk.rain, c.risk.snow,
      c.risk.combined, c.risk.load_override, c.weather_status, c.weather_missing_reason,
    ].map(cell).join(','),
  )
  return [HEADER.join(','), ...rows].join('\r\n') + '\r\n'
}

export function csvFilename(route: RouteAssessment): string {
  return `${route.id}-checkpoints-${route.departure_datetime.slice(0, 10)}.csv`
}

export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
