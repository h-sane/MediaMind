import { useEffect, useRef, useState } from 'react'

/**
 * True once the element has come within 300px of the viewport — and stays
 * true (sticky), so a fetched thumbnail is never re-fetched or revoked by
 * scrolling away. Keeps huge grids cheap: only visible tiles hit the API,
 * and the 300px margin means the next screenful is already loading by the
 * time the user scrolls to it.
 */
export function useNearViewport<T extends HTMLElement>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || visible) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setVisible(true)
      },
      { rootMargin: '300px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [visible])

  return [ref, visible]
}
