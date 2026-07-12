import { useEffect, useRef, useState } from 'react'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'
import { Breadcrumb } from './Breadcrumb'

/**
 * Breadcrumb by default; clicking the empty space to the right of the
 * segments (or the trailing area of the bar) switches to a raw, editable
 * path field — Explorer's own address-bar behavior.
 */
export function AddressBar(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const navigate = useExplorerStore((s) => s.navigate)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!editing) return
    setDraft(isRealFolder(currentPath) ? currentPath : '')
  }, [editing, currentPath])

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  return (
    <div className="flex h-8 min-w-0 flex-1 items-center rounded-md border border-zinc-200 bg-white px-2">
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              navigate(draft.trim() === '' ? null : draft.trim())
              setEditing(false)
            } else if (e.key === 'Escape') {
              setEditing(false)
            }
          }}
          onBlur={() => setEditing(false)}
          placeholder="This PC"
          className="w-full text-sm text-zinc-900 outline-none"
        />
      ) : (
        <>
          <Breadcrumb />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="h-full flex-1"
            aria-label="Edit address"
          />
        </>
      )}
    </div>
  )
}
