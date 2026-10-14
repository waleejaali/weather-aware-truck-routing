const pad = (n: number, width = 2) => String(Math.trunc(Math.abs(n))).padStart(width, '0')

/**
 * Format an instant as ISO 8601 with an explicit UTC offset, e.g. 2026-10-14T08:00:00-07:00.
 * offsetMinutes is the zone's offset from UTC (negative west of Greenwich).
 */
export function formatIsoWithOffset(date: Date, offsetMinutes: number): string {
  const shifted = new Date(date.getTime() + offsetMinutes * 60_000)
  const sign = offsetMinutes < 0 ? '-' : '+'
  const abs = Math.abs(offsetMinutes)
  return (
    `${pad(shifted.getUTCFullYear(), 4)}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}` +
    `T${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}:${pad(shifted.getUTCSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  )
}

/** The browser's current UTC offset for a given instant, in minutes (west is negative). */
export function localOffsetMinutes(date: Date): number {
  return -date.getTimezoneOffset()
}

/**
 * Convert a <input type="datetime-local"> value (YYYY-MM-DDTHH:mm, no zone) into an ISO 8601
 * string with the browser's UTC offset. Returns null for invalid or non-existent local times.
 */
export function localInputToIso(value: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
  if (!m) return null
  const [y, mo, d, h, mi] = m.slice(1).map(Number)
  const date = new Date(y, mo - 1, d, h, mi)
  const roundTrips =
    date.getFullYear() === y &&
    date.getMonth() === mo - 1 &&
    date.getDate() === d &&
    date.getHours() === h &&
    date.getMinutes() === mi
  return roundTrips ? formatIsoWithOffset(date, localOffsetMinutes(date)) : null
}

/** Default form value: tomorrow 08:00 in the browser's time zone, as a datetime-local string. */
export function defaultDepartureLocal(now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 8, 0)
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Shift an ISO timestamp by whole hours; the result carries the browser's offset at that instant. */
export function shiftIsoByHours(iso: string, hours: number): string {
  const shifted = new Date(new Date(iso).getTime() + hours * 3_600_000)
  return formatIsoWithOffset(shifted, localOffsetMinutes(shifted))
}

const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

/** Render a backend timestamp (timezone-aware ISO 8601) in the user's local time zone. */
export function formatLocalDateTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : dateTimeFormat.format(date)
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours} h ${minutes} min` : `${minutes} min`
}

export function timeZoneLabel(now: Date = new Date()): string {
  const offset = localOffsetMinutes(now)
  const sign = offset < 0 ? '-' : '+'
  const abs = Math.abs(offset)
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return `${zone} (UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)})`
}
