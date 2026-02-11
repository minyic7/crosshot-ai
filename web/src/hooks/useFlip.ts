import { useRef, useCallback, useLayoutEffect } from 'react'

/**
 * FLIP animation hook — animates DOM elements smoothly between positions.
 *
 * Call `snapshot()` BEFORE a state change to capture current positions,
 * then after React re-renders, the hook auto-animates from old → new positions.
 */
export function useFlip(
  depKey: string,
  cellRefs: React.MutableRefObject<Record<string, HTMLElement | null>>,
  enabled = true,
) {
  const prevRects = useRef<Record<string, { x: number; y: number }>>({})

  const snapshot = useCallback(() => {
    const rects: Record<string, { x: number; y: number }> = {}
    for (const [id, el] of Object.entries(cellRefs.current)) {
      if (el) {
        const r = el.getBoundingClientRect()
        rects[id] = { x: r.left, y: r.top }
      }
    }
    prevRects.current = rects
  }, [cellRefs])

  useLayoutEffect(() => {
    if (!enabled) return
    const prev = prevRects.current
    if (Object.keys(prev).length === 0) return

    for (const [id, el] of Object.entries(cellRefs.current)) {
      if (!el || !prev[id]) continue
      const newR = el.getBoundingClientRect()
      const dx = prev[id].x - newR.x
      const dy = prev[id].y - newR.y
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue

      el.getAnimations().forEach((a) => a.cancel())
      el.animate(
        [
          { transform: `translate(${dx}px, ${dy}px)` },
          { transform: 'translate(0, 0)' },
        ],
        { duration: 300, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
      )
    }
  }, [depKey, enabled, cellRefs])

  return snapshot
}
