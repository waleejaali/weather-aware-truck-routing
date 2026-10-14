import type { RiskKey, RiskMiles } from '../api/types'
import { ALL_RISK_META, RISK_ORDER, riskMeta } from '../lib/risk'

/** A risk label with a shape glyph and text, so the level never depends on colour alone. */
export function RiskBadge({ level, prefix, size = 'sm' }: { level: RiskKey | null; prefix?: string; size?: 'xs' | 'sm' }) {
  const meta = riskMeta(level)
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-semibold ${
        size === 'xs' ? 'px-1.5 py-px text-[11px]' : 'px-2 py-0.5 text-xs'
      }`}
      style={{ background: meta.bg, color: meta.fg, borderColor: meta.color }}
    >
      <span aria-hidden="true">{meta.symbol}</span>
      {prefix ? <span className="font-normal">{prefix}</span> : null}
      {meta.label}
    </span>
  )
}

/** Quiet inline variant for dense places (tables, cards): a coloured glyph followed by the level as text. */
export function RiskDot({ level, suffix = '', size = 'sm' }: { level: RiskKey | null; suffix?: string; size?: 'xs' | 'sm' }) {
  const meta = riskMeta(level)
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-ink ${size === 'xs' ? 'text-xs' : 'text-sm'}`}>
      <span aria-hidden="true" style={{ color: meta.color }} className="text-[11px] leading-none">
        {meta.symbol}
      </span>
      {meta.label}
      {suffix}
    </span>
  )
}

const miles = (n: number) => `${n.toLocaleString('en-US', { maximumFractionDigits: 0 })} mi`

/** Stacked bar of estimated risk miles plus an exact text legend. */
export function RiskMilesBar({ miles: m }: { miles: RiskMiles }) {
  const values = ALL_RISK_META.map((meta) => ({ meta, value: m[meta.key] }))
  const total = values.reduce((sum, v) => sum + v.value, 0) || 1
  const description = values.map((v) => `${v.meta.label} ${miles(v.value)}`).join(', ')
  return (
    <div>
      <div
        role="img"
        aria-label={`Estimated miles by risk level: ${description}`}
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-line"
      >
        {values
          .filter((v) => v.value > 0)
          .map(({ meta, value }) => (
            <div
              key={meta.key}
              title={`${meta.label}: ${miles(value)}`}
              style={{
                width: `${(value / total) * 100}%`,
                background:
                  meta.key === 'unknown'
                    ? `repeating-linear-gradient(45deg, ${meta.color}, ${meta.color} 4px, #cfd8dc 4px, #cfd8dc 8px)`
                    : meta.color,
              }}
            />
          ))}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        {values.map(({ meta, value }) => (
          <div key={meta.key} className="flex items-center justify-between gap-2">
            <dt>
              <RiskBadge level={meta.key === 'unknown' ? null : (meta.key as RiskKey)} size="xs" />
            </dt>
            <dd className="whitespace-nowrap tabular-nums text-muted">{miles(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export { RISK_ORDER }
