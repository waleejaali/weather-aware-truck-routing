export function formatMiles(n: number, digits = 0): string {
  return `${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })} mi`
}
