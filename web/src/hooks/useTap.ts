import { useRef, useCallback, type TouchEvent } from 'react'

/**
 * Distinguishes a tap from a scroll on touch devices.
 * Uses touchEnd (not touchMove) to measure displacement — more reliable
 * on iOS Safari where touchMove events are suppressed during native scroll.
 * Desktop clicks pass through normally.
 */
export function useTap(handler: () => void, threshold = 10) {
  const touch = useRef({ y: 0, scrolled: false, active: false })

  const onTouchStart = useCallback((e: TouchEvent) => {
    touch.current = { y: e.touches[0].clientY, scrolled: false, active: true }
  }, [])

  const onTouchEnd = useCallback((e: TouchEvent) => {
    const dy = Math.abs(e.changedTouches[0].clientY - touch.current.y)
    if (dy > threshold) touch.current.scrolled = true
  }, [threshold])

  const onClick = useCallback(() => {
    if (touch.current.active) {
      // Touch interaction — only fire if finger didn't scroll
      if (!touch.current.scrolled) handler()
      touch.current.active = false
    } else {
      // Desktop mouse click — always fire
      handler()
    }
  }, [handler])

  return { onTouchStart, onTouchEnd, onClick }
}
