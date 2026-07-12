/**
 * Persistent log file for the main process, the engine's stdio, and
 * forwarded renderer errors — all in one place so a crashed session can
 * still be inspected afterwards (the dev terminal scrolls away/closes).
 */
import { createWriteStream, WriteStream } from 'node:fs'
import { join } from 'node:path'
import { app } from 'electron'

let stream: WriteStream | null = null

function getStream(): WriteStream {
  if (!stream) {
    const path = join(app.getPath('logs'), 'mediamind.log')
    stream = createWriteStream(path, { flags: 'a' })
  }
  return stream
}

export function logLine(source: string, message: string): void {
  const line = `${new Date().toISOString()} [${source}] ${message.trimEnd()}\n`
  getStream().write(line)
}

export function logPath(): string {
  return join(app.getPath('logs'), 'mediamind.log')
}
