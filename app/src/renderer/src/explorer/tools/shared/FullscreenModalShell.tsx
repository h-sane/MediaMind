import { useEffect } from 'react'
import { X } from 'lucide-react'

interface Props {
  /** Optional left rail (e.g. a list of items to jump between). */
  sidebar?: React.ReactNode
  /** Left side of the header bar — title text, prev/next nav, etc. */
  headerLeft: React.ReactNode
  /** Extra controls in the header bar, before the close button. */
  headerRight?: React.ReactNode
  onClose: () => void
  /** While true, Escape is left for a dialog stacked above this one to handle. */
  suppressEscape?: boolean
  bodyRef?: React.Ref<HTMLDivElement>
  children: React.ReactNode
}

/**
 * Shared chrome for a fullscreen dark review modal: backdrop, header bar
 * with a close button, and Escape-to-close — extracted from the dedupe
 * tool's `DuplicateGalleryModal` so other review surfaces (outlier
 * approval, etc.) get the same interaction pattern without duplicating it.
 * Matches `DuplicateGalleryModal`'s original behavior exactly: no
 * click-away-to-close on the backdrop, only Escape and the explicit X.
 */
export function FullscreenModalShell({
  sidebar,
  headerLeft,
  headerRight,
  onClose,
  suppressEscape,
  bodyRef,
  children
}: Props): React.JSX.Element {
  useEffect(() => {
    if (suppressEscape) return
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, suppressEscape])

  return (
    <div className="fixed inset-0 z-[70] flex bg-zinc-950">
      {sidebar}
      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-3">
          <div className="flex items-center gap-3">{headerLeft}</div>
          <div className="flex items-center gap-3">
            {headerRight}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div ref={bodyRef} className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  )
}
