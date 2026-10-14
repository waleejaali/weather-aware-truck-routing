const pad = (n: number, width = 2) => String(Math.trunc(Math.abs(n))).padStart(width, '0')

export function formatIsoWithOffset(date: Date, offsetMinutes: number): string {
  // Shift then read UTC fields so the output doesn't depend on the browser's own zone.
  const shifted = new Date(date.getTime() + offsetMinutes * 60_000)
  const sign = offsetMinutes < 0 ? '-' : '+'
  const abs = Math.abs(offsetMinutes)
  return (
    `${pad(shifted.getUTCFullYear(), 4)}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}` +
    `T${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}:${pad(shifted.getUTCSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  )
}

export function localOffsetMinutes(date: Date): number {
  // getTimezoneOffset() is positive west of UTC, the opposite of ISO 8601.
  return -date.getTimezoneOffset()
}

export function localInputToIso(value: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
  if (!m) return null
  const [y, mo, d, h, mi] = m.slice(1).map(Number)
  const date = new Date(y, mo - 1, d, h, mi)
  // Date silently rolls over invalid or DST-gap times, so reject anything that doesn't round-trip.
  const roundTrips =
    date.getFullYear() === y &&
    date.getMonth() === mo - 1 &&
    date.getDate() === d &&
    date.getHours() === h &&
    date.getMinutes() === mi
  return roundTrips ? formatIsoWithOffset(date, localOffsetMinutes(date)) : null
}

export function defaultDepartureLocal(now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 8, 0)
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

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

/** 16 h 17 min -> "16h 17m", for big card numbers. */
export function compactDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`
}

export function timeZoneLabel(now: Date = new Date()): string {
  const offset = localOffsetMinutes(now)
  const sign = offset < 0 ? '-' : '+'
  const abs = Math.abs(offset)
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return `${zone} (UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)})`
}
