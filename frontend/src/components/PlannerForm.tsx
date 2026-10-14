import type { FormEvent, ReactNode } from 'react'
import { CHECKPOINT_INTERVALS, type CheckpointInterval } from '../api/types'
import { PRESETS, type TripPreset } from '../lib/presets'
import { MAX_LOAD_LB, type FormErrors, type FormField, type FormValues } from '../lib/validation'

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
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-800">
        {label}
      </label>
      {children}
      {hint && !error ? <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      {error ? (
        <p id={`${id}-error`} className="mt-1 text-xs font-medium text-red-700">
          {error}
        </p>
      ) : null}
    </div>
  )
}

const inputClass = (error?: string) =>
  `block w-full rounded-md border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
    error ? 'border-red-600' : 'border-slate-300'
  }`

export function PlannerForm({ values, errors, generalError, submitting, timeZone, onChange, onPreset, onSubmit }: Props) {
  const handle = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }
  const text = (field: FormField, id: string, label: string, extra: { hint?: string; type?: string; inputMode?: 'decimal' | 'numeric'; placeholder?: string } = {}) => (
    <Field id={id} label={label} error={errors[field]} hint={extra.hint}>
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
        className={inputClass(errors[field])}
      />
    </Field>
  )

  return (
    <form onSubmit={handle} noValidate aria-label="Trip details" className="space-y-5">
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-slate-900">Origin</legend>
        <div className="grid grid-cols-2 gap-3">
          {text('originLat', 'origin-lat', 'Latitude', { placeholder: '34.0522' })}
          {text('originLon', 'origin-lon', 'Longitude', { placeholder: '-118.2437' })}
        </div>
      </fieldset>
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-slate-900">Destination</legend>
        <div className="grid grid-cols-2 gap-3">
          {text('destLat', 'dest-lat', 'Latitude', { placeholder: '32.7767' })}
          {text('destLon', 'dest-lon', 'Longitude', { placeholder: '-96.7970' })}
        </div>
      </fieldset>
      <p className="-mt-2 text-xs text-slate-500">
        The routing API takes coordinates (decimal degrees), not street addresses. Quick fill:
      </p>
      <div className="-mt-3 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            type="button"
            onClick={() => onPreset(p)}
            className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {p.name}
          </button>
        ))}
      </div>

      {text('departureLocal', 'departure', 'Departure date and time', {
        type: 'datetime-local',
        inputMode: undefined,
        hint: `Your local time: ${timeZone}. Sent to the API with its UTC offset.`,
      })}
      {text('loadLb', 'load', 'Load weight (lb)', {
        inputMode: 'numeric',
        placeholder: '42000',
        hint: `Up to ${MAX_LOAD_LB.toLocaleString('en-US')} lb. Heavy loads raise wind risk.`,
      })}

      <fieldset>
        <legend className="mb-1 text-sm font-medium text-slate-800">Weather checkpoint spacing</legend>
        <div className="flex gap-2" role="radiogroup" aria-describedby={errors.interval ? 'interval-error' : undefined}>
          {CHECKPOINT_INTERVALS.map((miles) => (
            <label
              key={miles}
              className={`flex-1 cursor-pointer rounded-md border px-3 py-2 text-center text-sm font-medium focus-within:ring-2 focus-within:ring-indigo-500 ${
                values.interval === miles ? 'border-indigo-600 bg-indigo-50 text-indigo-900' : 'border-slate-300 bg-white text-slate-700'
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
        <p className="mt-1 text-xs text-slate-500">Weather is sampled at checkpoints this far apart; closer spacing checks more of the road.</p>
        {errors.interval ? <p id="interval-error" className="mt-1 text-xs font-medium text-red-700">{errors.interval}</p> : null}
      </fieldset>

      {generalError ? (
        <p role="alert" className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {generalError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {submitting ? (
          <>
            <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Assessing routes…
          </>
        ) : (
          'Assess Routes'
        )}
      </button>
    </form>
  )
}
