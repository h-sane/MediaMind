/**
 * Standalone check for the destructive purge logic. Run:
 *   node src/main/purge.test.ts
 * Simulates an offline drive with a non-existent drive letter (Z:\), so no real
 * data or removable hardware is needed.
 */
import assert from 'node:assert'
import { mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { purge, readDataLocations } from './purge.ts'

const sandbox = join(tmpdir(), `mm-purge-test-${Date.now()}`)
const central = join(sandbox, 'MediaMind')
const lib1 = join(sandbox, 'lib1') // reachable (real temp dir on an existing drive)
const OFFLINE = 'Z:\\offlinelib' // unreachable: assumes no Z: drive is mounted

function touch(p: string): void {
  mkdirSync(join(p, '..'), { recursive: true })
  writeFileSync(p, 'x')
}

// --- build the sandbox ------------------------------------------------------
mkdirSync(central, { recursive: true })
writeFileSync(
  join(central, 'libraries.json'),
  JSON.stringify({ libraries: [
    { id: 'a', path: lib1, name: 'Reachable Lib' },
    { id: 'b', path: OFFLINE, name: 'Offline Lib' }
  ] })
)
// Central data artifacts + a WAL sibling, plus things that MUST survive.
touch(join(central, 'settings.json'))
touch(join(central, 'global_people.sqlite3'))
touch(join(central, 'global_people.sqlite3-wal'))
mkdirSync(join(central, 'thumb_cache'), { recursive: true })
touch(join(central, 'thumb_cache', 'a.jpg'))
mkdirSync(join(central, 'logs'), { recursive: true })
touch(join(central, 'logs', 'mediamind.log')) // must survive (diagnostics, held open)
mkdirSync(join(central, 'Cache'), { recursive: true })
touch(join(central, 'Cache', 'chromium')) // Electron's own cache — must survive
mkdirSync(join(lib1, '.mediamind'), { recursive: true })
touch(join(lib1, '.mediamind', 'index.db'))
touch(join(lib1, 'photo.jpg')) // user media — must NEVER be touched

// --- enumeration ------------------------------------------------------------
const locs = readDataLocations(central)
assert.equal(locs.length, 3, 'two libraries + central')
const reachable = locs.find((l) => l.label === 'Reachable Lib')!
const offline = locs.find((l) => l.label === 'Offline Lib')!
assert.equal(reachable.reachable, true, 'temp-dir library is reachable')
assert.equal(offline.reachable, false, 'Z: library is unreachable')

// --- purge without skip: must delete NOTHING and report the offline lib -----
const blocked = purge(central, false)
assert.equal(blocked.done, false, 'blocked when an offline drive is present')
assert.deepEqual(blocked.unreachable, ['Offline Lib'])
assert.equal(blocked.deleted.length, 0, 'nothing deleted while blocked')
assert.ok(existsSync(join(lib1, '.mediamind')), 'reachable lib untouched while blocked')
assert.ok(existsSync(join(central, 'settings.json')), 'central untouched while blocked')

// --- purge with skip: delete reachable + central, keep offline/logs/cache ---
const done = purge(central, true)
assert.equal(done.done, true)
assert.ok(!existsSync(join(lib1, '.mediamind')), 'reachable .mediamind deleted')
assert.ok(existsSync(join(lib1, 'photo.jpg')), 'USER MEDIA MUST SURVIVE')
assert.ok(!existsSync(join(central, 'settings.json')), 'central artifact deleted')
assert.ok(!existsSync(join(central, 'global_people.sqlite3')), 'central sqlite deleted')
assert.ok(!existsSync(join(central, 'global_people.sqlite3-wal')), 'WAL sibling deleted')
assert.ok(!existsSync(join(central, 'thumb_cache')), 'thumb_cache dir deleted')
assert.ok(existsSync(join(central, 'logs', 'mediamind.log')), 'logs preserved (held open)')
assert.ok(existsSync(join(central, 'Cache', 'chromium')), "Electron's own cache preserved")

rmSync(sandbox, { recursive: true, force: true })
console.log('purge.test.ts: all assertions passed')
