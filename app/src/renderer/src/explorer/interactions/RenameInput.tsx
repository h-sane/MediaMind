import { useEffect, useRef, useState } from 'react'
import { useFsRename } from '../../api/hooks'
import { useSelectionStore } from '../../stores/selection'

interface Props {
  path: string
  name: string
  isFile: boolean
  /** The folder currently being viewed — always the item's parent, since
   * rename only ever targets something visible in the open folder. */
  folder: string
  className?: string
}

const ILLEGAL_CHARS = /[<>:"/\\|?*]/

/** Replaces an item's name label while `renamingPath` targets it. Mirrors
 * Explorer's stem-selected, extension-excluded editing for files (whole name
 * for folders); the backend re-validates, this is just fast local feedback. */
export function RenameInput({ path, name, isFile, folder, className }: Props): React.JSX.Element {
  const endRename = useSelectionStore((s) => s.endRename)
  const renameMutation = useFsRename()
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState(name)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    function focusAndSelect(): void {
      input!.focus()
      const dot = name.lastIndexOf('.')
      if (isFile && dot > 0) {
        input!.setSelectionRange(0, dot)
      } else {
        input!.select()
      }
    }
    focusAndSelect()
    // When this mounts right after a context-menu "Rename" selection, Radix's
    // own focus-restoration (returning focus to the trigger on menu close)
    // runs in a follow-up frame and wins the race against the focus() call
    // above — re-assert on the next frame so ours is the one that sticks.
    const raf = requestAnimationFrame(focusAndSelect)
    // Run once on mount only — re-selecting on every keystroke would fight the user.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => cancelAnimationFrame(raf)
  }, [])

  function validate(candidate: string): string | null {
    const trimmed = candidate.trim()
    if (!trimmed) return 'Name cannot be empty'
    if (ILLEGAL_CHARS.test(trimmed)) return 'Name cannot contain: < > : " / \\ | ? *'
    return null
  }

  function commit(): void {
    if (value === name) {
      endRename()
      return
    }
    const validationError = validate(value)
    if (validationError) {
      setError(validationError)
      return
    }
    renameMutation.mutate(
      { path, newName: value.trim(), folder },
      {
        onSuccess: () => endRename(),
        onError: (err) => setError(err instanceof Error ? err.message : 'Rename failed')
      }
    )
  }

  return (
    <span className="inline-flex min-w-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          setError(null)
        }}
        onKeyDown={(e) => {
          e.stopPropagation()
          if (e.key === 'Enter') commit()
          else if (e.key === 'Escape') endRename()
        }}
        onBlur={commit}
        disabled={renameMutation.isPending}
        className={
          className ??
          `w-full min-w-0 rounded border px-1 py-0 outline-none ${
            error ? 'border-red-400' : 'border-blue-500'
          }`
        }
      />
      {error && <span className="text-[10px] leading-tight text-red-500">{error}</span>}
    </span>
  )
}
