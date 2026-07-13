import { useEffect, useRef, useState } from 'react'
import { Terminal, Trash2, X } from 'lucide-react'
import { useDevLogStore, type LogLevel } from '../stores/devLog'

const LEVEL_ORDER: Record<LogLevel, number> = {
  DEBUG: 0,
  INFO: 1,
  WARNING: 2,
  ERROR: 3,
  CRITICAL: 4
}

const LEVEL_COLOR: Record<LogLevel, string> = {
  DEBUG: 'text-zinc-500',
  INFO: 'text-zinc-300',
  WARNING: 'text-amber-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-400'
}

const FILTERS: { label: string; min: LogLevel }[] = [
  { label: 'All', min: 'DEBUG' },
  { label: 'Info+', min: 'INFO' },
  { label: 'Warnings+', min: 'WARNING' },
  { label: 'Errors', min: 'ERROR' }
]

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString([], { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

/** Toggle button + panel for the in-app dev log console — see
 * devLogConfig.ts for the enable/disable switch. Fed by the WS "log"
 * channel (backend, api/progress.ts) and renderer errors (logDevError,
 * stores/devLog.ts), so a stuck scan or a swallowed exception is visible
 * without leaving the app or digging through log files. */
export function DevLogPanel(): React.JSX.Element {
  const open = useDevLogStore((s) => s.open)
  const toggleOpen = useDevLogStore((s) => s.toggleOpen)
  const entries = useDevLogStore((s) => s.entries)
  const clear = useDevLogStore((s) => s.clear)
  const [minLevel, setMinLevel] = useState<LogLevel>('DEBUG')
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  const visible = entries.filter((e) => LEVEL_ORDER[e.level] >= LEVEL_ORDER[minLevel])

  useEffect(() => {
    if (!open || !autoScroll) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [open, autoScroll, visible.length])

  function handleScroll(): void {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
    setAutoScroll(atBottom)
  }

  return (
    <>
      <button
        type="button"
        onClick={toggleOpen}
        title="Dev log console"
        className={`fixed bottom-3 right-3 z-[70] flex h-9 w-9 items-center justify-center rounded-full shadow-lg transition ${
          open ? 'bg-zinc-900 text-white' : 'bg-white text-zinc-500 hover:text-zinc-800'
        } border border-zinc-200`}
      >
        <Terminal className="h-4 w-4" />
      </button>

      {open && (
        <div className="fixed inset-x-0 bottom-0 z-[65] flex h-72 flex-col border-t border-zinc-700 bg-zinc-900 text-xs text-zinc-200 shadow-2xl">
          <div className="flex shrink-0 items-center justify-between border-b border-zinc-700 px-3 py-1.5">
            <div className="flex items-center gap-2">
              <Terminal className="h-3.5 w-3.5 text-zinc-400" />
              <span className="font-medium text-zinc-300">Dev log</span>
              <span className="text-zinc-500">
                {visible.length}
                {visible.length !== entries.length ? ` / ${entries.length}` : ''}
              </span>
            </div>
            <div className="flex items-center gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.min}
                  type="button"
                  onClick={() => setMinLevel(f.min)}
                  className={`rounded px-2 py-0.5 ${
                    minLevel === f.min ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  {f.label}
                </button>
              ))}
              <button
                type="button"
                onClick={clear}
                title="Clear"
                className="ml-1 rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={toggleOpen}
                title="Close"
                className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-3 py-2 font-mono">
            {visible.length === 0 ? (
              <p className="text-zinc-600">No log entries yet.</p>
            ) : (
              visible.map((e) => (
                <div key={e.id} className="flex gap-2 py-0.5 leading-tight">
                  <span className="shrink-0 text-zinc-600">{formatTime(e.ts)}</span>
                  <span className={`w-16 shrink-0 font-medium ${LEVEL_COLOR[e.level]}`}>{e.level}</span>
                  <span className="shrink-0 text-zinc-500">{e.logger}</span>
                  <span className="whitespace-pre-wrap break-all text-zinc-200">{e.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </>
  )
}
