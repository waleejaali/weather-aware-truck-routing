/** A weather reading with its unit, or an explicit "No data" - never a zero standing in for a missing value. */
export function Reading({ value, unit, digits = 1 }: { value: number | null; unit: string; digits?: number }) {
  if (value === null || value === undefined) {
    return <span className="italic text-slate-500">No data</span>
  }
  return (
    <span className="tabular-nums">
      {value.toFixed(digits)} <span className="text-slate-500">{unit}</span>
    </span>
  )
}
