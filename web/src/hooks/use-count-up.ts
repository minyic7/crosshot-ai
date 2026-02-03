import { useState, useEffect, useRef } from "react"

/**
 * Animates a number from 0 to the target value.
 * Handles formatted strings like "1,284" by parsing to number and re-formatting.
 */
export function useCountUp(target: string, duration = 1000): string {
  const numericTarget = parseFloat(target.replace(/,/g, ""))
  const [current, setCurrent] = useState(0)
  const startTime = useRef<number | null>(null)
  const rafId = useRef<number>(0)

  useEffect(() => {
    if (isNaN(numericTarget)) {
      return
    }

    startTime.current = null

    function step(timestamp: number) {
      if (!startTime.current) startTime.current = timestamp
      const elapsed = timestamp - startTime.current
      const progress = Math.min(elapsed / duration, 1)

      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setCurrent(Math.round(eased * numericTarget))

      if (progress < 1) {
        rafId.current = requestAnimationFrame(step)
      }
    }

    rafId.current = requestAnimationFrame(step)

    return () => cancelAnimationFrame(rafId.current)
  }, [numericTarget, duration])

  // Re-format with commas if original had them
  if (target.includes(",")) {
    return current.toLocaleString()
  }
  return String(current)
}
