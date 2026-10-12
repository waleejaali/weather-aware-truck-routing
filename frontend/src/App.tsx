import { useEffect, useState } from 'react'
import { fetchHealth } from './api/health'

type BackendState =
  | { kind: 'checking' }
  | { kind: 'ok'; service: string }
  | { kind: 'unreachable'; message: string }

function App() {
  const [backend, setBackend] = useState<BackendState>({ kind: 'checking' })

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then((health) => {
        if (!cancelled) setBackend({ kind: 'ok', service: health.service })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Unknown error'
          setBackend({ kind: 'unreachable', message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <h1 className="text-3xl font-semibold">Weather-Aware Truck Routing</h1>
      <p className="text-slate-600">Project foundation is running. Route planning is not implemented yet.</p>
      <div className="rounded-lg border border-slate-200 p-4" role="status">
        {backend.kind === 'checking' && <span>Checking backend…</span>}
        {backend.kind === 'ok' && (
          <span className="text-green-700">Backend reachable ({backend.service})</span>
        )}
        {backend.kind === 'unreachable' && (
          <span className="text-red-700">Backend unreachable: {backend.message}</span>
        )}
      </div>
    </main>
  )
}

export default App
