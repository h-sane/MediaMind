/**
 * WebSocket progress client — subscribes to WS /v1/progress and distributes
 * job updates into the Zustand jobs store. Terminal messages also invalidate
 * TanStack Query caches so dependent components re-fetch automatically.
 *
 * Mount as a side-effect hook in App.tsx once; it manages its own lifecycle.
 */
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { connectBackend } from './client'
import { useJobsStore } from '../stores/jobs'
import { useDevLogStore, type LogLevel } from '../stores/devLog'

export function useProgressSocket(): void {
  const qc = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const destroyedRef = useRef(false)

  useEffect(() => {
    destroyedRef.current = false

    async function connect(): Promise<void> {
      if (destroyedRef.current || wsRef.current) return

      let port: number
      let token: string
      try {
        const info = await connectBackend()
        port = info.port
        token = info.token
      } catch {
        return
      }
      if (destroyedRef.current) return

      const ws = new WebSocket(
        `ws://127.0.0.1:${port}/v1/progress?token=${encodeURIComponent(token)}`
      )
      wsRef.current = ws

      ws.onopen = () => {
        attemptRef.current = 0
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data as string) as Record<string, unknown>
          if (msg.msg_type === 'job') {
            const snap = {
              id: msg.id as string,
              library_id: msg.library_id as string,
              type: msg.type as string,
              state: msg.state as 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled',
              phase: (msg.phase ?? '') as string,
              done: (msg.done ?? 0) as number,
              total: (msg.total ?? 0) as number,
              error: (msg.error ?? '') as string,
              result: (msg.result ?? null) as Record<string, unknown> | null,
              created_at: (msg.created_at ?? Date.now() / 1000) as number,
              finished_at: (msg.finished_at ?? null) as number | null,
            }
            useJobsStore.getState().upsert(snap)
            const isTerminal = ['succeeded', 'failed', 'cancelled'].includes(snap.state)
            if (isTerminal) {
              qc.invalidateQueries({ queryKey: ['duplicates', snap.library_id] })
              qc.invalidateQueries({ queryKey: ['persons', snap.library_id] })
              qc.invalidateQueries({ queryKey: ['multi-person', snap.library_id] })
              qc.invalidateQueries({ queryKey: ['providers'] })
            }
          } else if (msg.msg_type === 'log') {
            useDevLogStore.getState().push({
              ts: (msg.ts ?? Date.now() / 1000) as number,
              level: (msg.level ?? 'INFO') as LogLevel,
              logger: (msg.logger ?? '') as string,
              message: (msg.message ?? '') as string
            })
          }
        } catch {
          /* malformed message — ignore */
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onclose = () => {
        wsRef.current = null
        if (!destroyedRef.current) {
          const delay = Math.min(500 * 2 ** attemptRef.current, 5000)
          attemptRef.current++
          timerRef.current = setTimeout(() => void connect(), delay)
        }
      }
    }

    void connect()

    return () => {
      destroyedRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [qc])
}
