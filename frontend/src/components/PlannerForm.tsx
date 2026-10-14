import type { FormEvent, ReactNode } from 'react'
import { CHECKPOINT_INTERVALS, type CheckpointInterval } from '../api/types'
import { PRESETS, placeName, presetFor, type TripPreset } from '../lib/presets'
import { MAX_LOAD_LB, type FormErrors, type FormField, type FormValues } from '../lib/validation'
import { IconArrowRight, IconChevronDown, IconPin, IconShield, IconSliders } from './icons'

interface Props {
  values: FormValues
  errors: FormErrors
  generalError?: string | null
  submitting: boolean
  timeZone: string
  onChange: (field: FormField, value: string | CheckpointInterval) => void
  onPreset: (preset: TripPreset) => void
  onSubmit: () => void
}

function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-muted">
        {label}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-faint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs font-medium text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function PlannerForm({ values, errors, generalError, submitting, timeZone, onChange, onPreset, onSubmit }: Props) {
  const handle = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  const preset = presetFor(values)
  const originName = placeName(values.originLat, values.originLon) ?? 'Custom origin'
  const destName = placeName(values.destLat, values.destLon) ?? 'Custom destination'

  const text = (
    field: FormField,
    id: string,
    label: string,
    extra: { hint?: string; type?: string; inputMode?: 'decimal' | 'numeric'; placeholder?: string; suffix?: string } = {},
  ) => (
    <Field id={id} label={label} error={errors[field]} hint={extra.hint}>
      <div className="relative">
        <input
          id={id}
          name={field}
          type={extra.type ?? 'text'}
          inputMode={extra.inputMode ?? 'decimal'}
          autoComplete="off"
          placeholder={extra.placeholder}
          value={values[field] as string}
          onChange={(e) => onChange(field, e.target.value)}
          aria-invalid={errors[field] ? true : undefined}
          aria-describedby={errors[field] ? `${id}-error` : extra.hint ? `${id}-hint` : undefined}
          className={`input ${extra.suffix ? 'pr-10' : ''}`}
        />
        {extra.suffix ? <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-faint">{extra.suffix}</span> : null}
      </div>
    </Field>
  )

  return (
    <form onSubmit={handle} noValidate aria-label="Trip details" className="flex flex-col">
      <div className="space-y-6 p-6">
        <div>
          <label htmlFor="quick-trip" className="mb-1.5 block text-xs font-medium text-muted">
            Quick trip
          </label>
          <div className="relative">
            <select
              id="quick-trip"
              value={preset?.id ?? 'custom'}
              onChange={(e) => {
                const chosen = PRESETS.find((p) => p.id === e.target.value)
                if (chosen) onPreset(chosen)
              }}
              className="input appearance-none pr-10"
            >
              <option value="custom">Custom trip</option>
              {PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-faint" />
          </div>
          <p className="mt-1.5 text-xs text-faint">The routing API takes coordinates (decimal degrees), not street addresses.</p>
        </div>

        <fieldset className="space-y-3">
          <legend className="flex items-center gap-2 text-sm font-semibold text-ink">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-accent" />
            Origin
          </legend>
          <p className="text-lg font-bold text-ink">{originName}</p>
          <div className="grid grid-cols-2 gap-3">
            {text('originLat', 'origin-lat', 'Latitude', { placeholder: '34.0522' })}
            {text('originLon', 'origin-lon', 'Longitude', { placeholder: '-118.2437' })}
          </div>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="flex items-center gap-2 text-sm font-semibold text-ink">
            <IconPin size={16} className="text-accent" />
            Destination
          </legend>
          <p className="text-lg font-bold text-ink">{destName}</p>
          <div className="grid grid-cols-2 gap-3">
            {text('destLat', 'dest-lat', 'Latitude', { placeholder: '32.7767' })}
            {text('destLon', 'dest-lon', 'Longitude', { placeholder: '-96.7970' })}
          </div>
        </fieldset>

        <div className="space-y-5 border-t border-line pt-6">
          {text('departureLocal', 'departure', 'Departure date & time', {
            type: 'datetime-local',
            inputMode: undefined,
            hint: `Local time · ${timeZone}`,
          })}
          {text('loadLb', 'load', 'Load weight', {
            inputMode: 'numeric',
            placeholder: '42000',
            suffix: 'lb',
            hint: `Heavier loads can increase wind risk. Up to ${MAX_LOAD_LB.toLocaleString('en-US')} lb.`,
          })}
        </div>

        <details className="group rounded-xl border border-line" open={errors.interval ? true : undefined}>
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
            <IconSliders size={16} />
            Advanced settings
            <IconChevronDown size={16} className="ml-auto transition-transform group-open:rotate-180" />
          </summary>
          <div className="space-y-2 border-t border-line px-4 py-4">
            <p id="interval-label" className="text-xs font-medium text-muted">
              Weather checkpoint spacing
            </p>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-labelledby="interval-label" aria-describedby={errors.interval ? 'interval-error' : undefined}>
              {CHECKPOINT_INTERVALS.map((miles) => (
                <label
                  key={miles}
                  className={`cursor-pointer rounded-lg border px-3 py-2 text-center text-sm font-semibold focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent ${
                    values.interval === miles ? 'border-accent bg-accent/10 text-accent' : 'border-line-strong text-muted hover:text-ink'
                  }`}
                >
                  <input
                    type="radio"
                    name="interval"
                    value={miles}
                    checked={values.interval === miles}
                    onChange={() => onChange('interval', miles)}
                    className="sr-only"
                  />
                  {miles} mi
                </label>
              ))}
            </div>
            <p className="text-xs text-faint">Weather is sampled at checkpoints this far apart; closer spacing checks more of the road.</p>
            {errors.interval ? (
              <p id="interval-error" className="text-xs font-medium text-red-300">
                {errors.interval}
              </p>
            ) : null}
          </div>
        </details>

        {generalError ? (
          <p role="alert" className="rounded-xl border border-red-400/60 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {generalError}
          </p>
        ) : null}

        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? (
            <>
              <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-on-brand border-t-transparent" />
              Assessing routes…
            </>
          ) : (
            <>
              Assess routes
              <IconArrowRight size={18} />
            </>
          )}
        </button>
      </div>

      <p className="flex items-center gap-2 border-t border-line px-6 py-4 text-xs text-faint">
        <IconShield size={14} />
        Forecast-based insights. Not a safety guarantee.
      </p>
    </form>
  )
}
