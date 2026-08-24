/**
 * Pure filesystem logic for "Remove all MediaMind data" — kept free of any
 * Electron import so it can be unit-tested against a throwaway sandbox (this is
 * a destructive, irreversible path; it must be verifiable). The Electron
 * plumbing (resolving the central dir, stopping the backend, relaunching) lives
 * in index.ts; everything that actually reads the registry and deletes folders
 * lives here.
 */
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { join, parse as parsePath } from 'node:path'
import type { DataLocation, PurgeResult } from '../shared/types'

/** MediaMind's own data artifacts inside the central store, by name. We delete
 * these explicitly rather than the whole folder because the central store is
 * shared with Electron's Chromium caches (locked while running) and our own
 * log file (kept open by log.ts) — an allowlist can neither break Electron nor
 * fail on a lock. Mirror any new `config.app_data_dir()` artifact here; `logs/`
 * is deliberately omitted (diagnostics, and held open by the main process). */
export const CENTRAL_DATA_ENTRIES = [
  'libraries.json',
  'settings.json',
  'quick_access.json',
  'recent_files.json',
  'browse_index.sqlite3',
  'folder_stats.sqlite3',
  'discovery.sqlite3',
  'global_people.sqlite3',
  'thumb_cache',
  'models',
  'fs_ops',
  'global_moves'
]

/** True when the drive that holds `p` is currently connected — its root anchor
 * (e.g. `D:\`) exists. An unmounted vault/removable drive fails this. */
export function driveReachable(p: string): boolean {
  const root = parsePath(p).root
  return root ? existsSync(root) : true
}

/** Read the library registry to list every deletable location. Pure filesystem
 * — works even while the backend is stopped, so the retry loop (reconnect a
 * drive, re-enumerate) never needs the engine. */
export function readDataLocations(centralDir: string): DataLocation[] {
  const out: DataLocation[] = []
  try {
    const reg = JSON.parse(readFileSync(join(centralDir, 'libraries.json'), 'utf-8'))
    for (const lib of reg.libraries ?? []) {
      out.push({
        kind: 'library',
        label: lib.name || lib.path,
        path: join(lib.path, '.mediamind'),
        reachable: driveReachable(lib.path)
      })
    }
  } catch {
    // No registry (nothing registered) or unreadable — only central data remains.
  }
  out.push({
    kind: 'central',
    label: 'App data (recognized people, indexes, settings)',
    path: centralDir,
    reachable: true
  })
  return out
}

/** Delete every reachable library's `.mediamind/` plus the central store's
 * known data artifacts. When a library's drive is offline and `skipUnreachable`
 * is false, deletes NOTHING and returns `done: false` so the caller can offer
 * connect-and-retry or skip — this keeps the registry intact for the retry.
 * Only ever removes MediaMind's own folders, never the user's media. */
export function purge(centralDir: string, skipUnreachable: boolean): PurgeResult {
  const locs = readDataLocations(centralDir)
  const unreachable = locs.filter((l) => l.kind === 'library' && !l.reachable)
  if (unreachable.length > 0 && !skipUnreachable) {
    return { done: false, deleted: [], failed: [], unreachable: unreachable.map((l) => l.label) }
  }

  const deleted: string[] = []
  const failed: { path: string; error: string }[] = []
  const removeDir = (path: string): void => {
    try {
      rmSync(path, { recursive: true, force: true })
      deleted.push(path)
    } catch (err) {
      failed.push({ path, error: err instanceof Error ? err.message : String(err) })
    }
  }

  for (const loc of locs) {
    if (loc.kind === 'library' && loc.reachable && existsSync(loc.path)) removeDir(loc.path)
  }
  for (const name of CENTRAL_DATA_ENTRIES) {
    const base = join(centralDir, name)
    if (existsSync(base)) removeDir(base)
    if (name.endsWith('.sqlite3')) {
      for (const suffix of ['-wal', '-shm']) {
        if (existsSync(base + suffix)) removeDir(base + suffix)
      }
    }
  }

  return { done: true, deleted, failed, unreachable: unreachable.map((l) => l.label) }
}
