import { create } from 'zustand'

interface ClickModifiers {
  ctrl: boolean
  shift: boolean
}

/** A minimal, layout-agnostic view of an entry for type-ahead name
 * matching — kept separate from `content/useDirectoryListing.ts`'s richer
 * `DirEntry` so this store doesn't depend on a content-pane type. */
export interface TypeAheadCandidate {
  path: string
  name: string
}

const TYPE_AHEAD_TIMEOUT_MS = 1000

interface SelectionStore {
  selected: Set<string>
  anchorPath: string | null
  /** The single entry with keyboard focus — independent of `selected`
   * (standard Explorer semantics: Ctrl+Arrow moves focus without changing
   * the selection at all). Reset whenever a view resets selection on
   * folder change (see `selection/useSelectionModel.ts`). */
  focusedPath: string | null
  renamingPath: string | null
  typeAheadBuffer: string
  typeAheadTime: number

  /** Explorer-exact click semantics: plain click replaces the selection;
   * ctrl+click toggles one item; shift+click selects the range between the
   * last anchor and `path` (ctrl+shift unions the range with the existing
   * selection). `orderedPaths` must be in visual order so range selection
   * matches what the user sees. */
  click: (path: string, modifiers: ClickModifiers, orderedPaths: string[]) => void
  setSelected: (paths: string[]) => void
  selectAll: (orderedPaths: string[]) => void
  /** Flips every entry's membership — Explorer's own "Invert selection". */
  invertSelection: (orderedPaths: string[]) => void
  clear: () => void
  beginRename: (path: string) => void
  endRename: () => void

  /** Arrow-key focus movement to `path` (the caller resolves `path` from
   * the current focus + a row/column delta). Ctrl alone moves focus only;
   * Shift extends the range selection from the existing anchor; a plain
   * arrow press replaces the selection and re-anchors on `path` — the same
   * modifier semantics as `click`, just keyed by the destination instead of
   * a pointer event. */
  moveFocus: (path: string, modifiers: ClickModifiers, orderedPaths: string[]) => void
  /** Type-ahead-to-select: `candidates` must be in visual order. Repeated
   * presses of the same single letter within the timeout cycle through
   * every name starting with that letter; typing several different letters
   * within the timeout narrows to a name-prefix match instead — standard
   * Windows Explorer behavior. */
  typeAhead: (char: string, candidates: TypeAheadCandidate[]) => void
}

export const useSelectionStore = create<SelectionStore>((set, get) => ({
  selected: new Set(),
  anchorPath: null,
  focusedPath: null,
  renamingPath: null,
  typeAheadBuffer: '',
  typeAheadTime: 0,

  click: (path, { ctrl, shift }, orderedPaths) => {
    const { selected, anchorPath } = get()

    if (shift && anchorPath) {
      const anchorIdx = orderedPaths.indexOf(anchorPath)
      const targetIdx = orderedPaths.indexOf(path)
      if (anchorIdx === -1 || targetIdx === -1) {
        set({ selected: new Set([path]), anchorPath: path, focusedPath: path })
        return
      }
      const [start, end] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx]
      const range = orderedPaths.slice(start, end + 1)
      set({ selected: ctrl ? new Set([...selected, ...range]) : new Set(range), focusedPath: path })
      return
    }

    if (ctrl) {
      const next = new Set(selected)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      set({ selected: next, anchorPath: path, focusedPath: path })
      return
    }

    set({ selected: new Set([path]), anchorPath: path, focusedPath: path })
  },

  setSelected: (paths) => set({ selected: new Set(paths) }),

  selectAll: (orderedPaths) => set({ selected: new Set(orderedPaths), anchorPath: orderedPaths[0] ?? null }),

  invertSelection: (orderedPaths) => {
    const { selected } = get()
    const next = orderedPaths.filter((p) => !selected.has(p))
    set({ selected: new Set(next), anchorPath: next[0] ?? null })
  },

  clear: () => set({ selected: new Set(), anchorPath: null, focusedPath: null }),

  beginRename: (path) => set({ renamingPath: path }),
  endRename: () => set({ renamingPath: null }),

  moveFocus: (path, { ctrl, shift }, orderedPaths) => {
    if (ctrl) {
      set({ focusedPath: path })
      return
    }
    if (shift) {
      const anchor = get().anchorPath ?? path
      const anchorIdx = orderedPaths.indexOf(anchor)
      const targetIdx = orderedPaths.indexOf(path)
      if (anchorIdx === -1 || targetIdx === -1) {
        set({ selected: new Set([path]), anchorPath: path, focusedPath: path })
        return
      }
      const [start, end] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx]
      set({ selected: new Set(orderedPaths.slice(start, end + 1)), anchorPath: anchor, focusedPath: path })
      return
    }
    set({ selected: new Set([path]), anchorPath: path, focusedPath: path })
  },

  typeAhead: (char, candidates) => {
    if (candidates.length === 0) return
    const now = Date.now()
    const { typeAheadBuffer, typeAheadTime, focusedPath } = get()
    const isContinuation = now - typeAheadTime < TYPE_AHEAD_TIMEOUT_MS
    const buffer = isContinuation ? typeAheadBuffer + char : char
    set({ typeAheadBuffer: buffer, typeAheadTime: now })

    const isSingleRepeatedChar = buffer.length > 1 && [...buffer].every((c) => c === buffer[0])
    const query = (isSingleRepeatedChar ? buffer[0] : buffer).toLowerCase()
    const matches = candidates.filter((c) => c.name.toLowerCase().startsWith(query))
    if (matches.length === 0) return

    const target = isSingleRepeatedChar
      ? matches[(matches.findIndex((m) => m.path === focusedPath) + 1) % matches.length]
      : matches[0]
    set({ selected: new Set([target.path]), anchorPath: target.path, focusedPath: target.path })
  }
}))
