import { useRef, useCallback, type TouchEvent } from 'react'

/**
 * Returns touch + click handlers that distinguish a tap from a scroll.
 * On mobile, onClick is suppressed if the finger moved > threshold during touch.
 * On desktop, onClick fires normally.
 */
export function useTap(handler: () => void, threshold = 8) {
  const moved = useRef(false)
  const startY = useRef(0)

  const onTouchStart = useCallback((e: TouchEvent) => {
    startY.current = e.touches[0].clientY
    moved.current = false
  }, [])

  const onTouchMove = useCallback((e: TouchEvent) => {
    if (Math.abs(e.touches[0].clientY - startY.current) > threshold) {
      moved.current = true
    }
  }, [threshold])

  const onClick = useCallback(() => {
    if (!moved.current) handler()
  }, [handler])

  return { onTouchStart, onTouchMove, onClick }
}
