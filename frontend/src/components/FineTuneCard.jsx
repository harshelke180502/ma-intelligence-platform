import { useState, useEffect, useCallback } from 'react'
import { startFinetuning, getFinetuningStatus } from '../api/client'

// Poll every 15 s while a job is active; stop when idle / succeeded / failed
const ACTIVE_PHASES = new Set(['sampling', 'labeling', 'uploading', 'training'])
const POLL_INTERVAL_MS = 15_000

const PHASE_LABELS = {
  idle:      'Not started',
  sampling:  'Sampling companies…',
  labeling:  'Labeling with GPT-4o…',
  uploading: 'Uploading training data…',
  training:  'Training on OpenAI…',
  succeeded: 'Fine-tuned',
  failed:    'Failed',
}

const PHASE_COLOR = {
  idle:      'text-gray-400',
  sampling:  'text-blue-600',
  labeling:  'text-blue-600',
  uploading: 'text-blue-600',
  training:  'text-blue-600',
  succeeded: 'text-green-600',
  failed:    'text-red-500',
}

function ProgressBar({ phase, labeled, total }) {
  if (!ACTIVE_PHASES.has(phase)) return null

  // Build progress percentage from labeled count during labeling phase;
  // show indeterminate bar for other active phases
  const pct =
    phase === 'labeling' && total > 0
      ? Math.round((labeled / total) * 100)
      : phase === 'sampling' ? 5
      : phase === 'uploading' ? 88
      : phase === 'training' ? null   // indeterminate
      : 0

  return (
    <div className="mt-2">
      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
        {pct !== null ? (
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        ) : (
          // Indeterminate slide animation for the training phase
          <div className="h-full w-1/3 bg-blue-400 rounded-full animate-[slide_1.5s_ease-in-out_infinite]" />
        )}
      </div>
      {phase === 'labeling' && (
        <p className="text-xs text-gray-400 mt-0.5">{labeled} / {total} examples labeled</p>
      )}
    </div>
  )
}

export default function FineTuneCard() {
  const [status, setStatus] = useState(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)

  const fetchStatus = useCallback(() => {
    getFinetuningStatus()
      .then(setStatus)
      .catch(() => {})
  }, [])

  // Initial load
  useEffect(() => { fetchStatus() }, [fetchStatus])

  // Poll while a job is active
  useEffect(() => {
    if (!status) return
    if (!ACTIVE_PHASES.has(status.phase)) return

    const id = setInterval(fetchStatus, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [status, fetchStatus])

  const handleStart = async () => {
    setStarting(true)
    setError(null)
    try {
      await startFinetuning()
      // Immediate status refresh
      const s = await getFinetuningStatus()
      setStatus(s)
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || 'Unknown error'
      setError(msg)
    } finally {
      setStarting(false)
    }
  }

  const phase = status?.phase ?? 'idle'
  const isActive = ACTIVE_PHASES.has(phase)
  const modelId = status?.model_id

  // Trim long fine-tuned model IDs for display
  const modelDisplay = modelId
    ? modelId.length > 40
      ? modelId.slice(0, 38) + '…'
      : modelId
    : phase === 'succeeded'
    ? 'Unknown model'
    : 'Zero-shot GPT-4o-mini'

  return (
    <div className="bg-white rounded-lg border border-gray-200 px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-4">
      {/* Left: model info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Thesis Scorer Model
          </span>
          <span
            className={`text-xs font-semibold px-2 py-0.5 rounded ${
              phase === 'succeeded'
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-600'
            }`}
          >
            {phase === 'succeeded' ? 'Fine-tuned' : 'Zero-shot'}
          </span>
        </div>

        <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">
          {modelDisplay}
        </p>

        <p className={`text-xs mt-0.5 ${PHASE_COLOR[phase]}`}>
          {PHASE_LABELS[phase]}
          {isActive && (
            <span className="ml-1 inline-block w-1 h-1 bg-blue-500 rounded-full animate-pulse" />
          )}
        </p>

        {status?.message && isActive && (
          <p className="text-xs text-gray-400 mt-0.5 truncate">{status.message}</p>
        )}

        <ProgressBar
          phase={phase}
          labeled={status?.examples_labeled ?? 0}
          total={status?.examples_total ?? 100}
        />

        {error && (
          <p className="text-xs text-red-500 mt-1">{error}</p>
        )}
      </div>

      {/* Right: action button */}
      <div className="shrink-0">
        {phase === 'succeeded' ? (
          <button
            onClick={handleStart}
            disabled={starting}
            className="px-3 py-1.5 text-xs rounded border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 whitespace-nowrap"
          >
            Re-tune
          </button>
        ) : (
          <button
            onClick={handleStart}
            disabled={isActive || starting}
            className="px-3 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {isActive ? 'Training…' : 'Fine-tune Model'}
          </button>
        )}
      </div>
    </div>
  )
}
