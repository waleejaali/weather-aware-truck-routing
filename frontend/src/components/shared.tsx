// Show "No data" rather than 0 so missing weather never looks like calm weather.
export function Reading({ value, unit, digits = 1 }: { value: number | null; unit: string; digits?: number }) {
  if (value === null || value === undefined) {
    return <span className="italic text-faint">No data</span>
  }
  return (
    <span className="tabular-nums">
      {value.toFixed(digits)} <span className="text-faint">{unit}</span>
    </span>
  )
}
