import { useState, useRef, useCallback, useEffect } from 'react'

export type Zone = 'pin' | 'unpin'

interface CardRect {
  id: string
  x: number
  y: number
  w: number
  h: number
  cx: number
  cy: number
  zone: Zone
}

export interface ZoneDragState {
  activeId: string | null
  dragPos: { x: number; y: number }
  dragOffset: { x: number; y: number }
  hoverZone: Zone | null
  hoverIdx: number | null
  activeRect: CardRect | null
}

interface UseZoneDragOptions {
  pinnedIds: string[]
  unpinnedIds: string[]
  cellRefs: React.MutableRefObject<Record<string, HTMLElement | null>>
  flipSnap: () => void
  onDrop: (id: string, targetZone: Zone, insertIdx: number) => void
}

const DRAG_THRESHOLD = 8

export function useZoneDrag({
  pinnedIds,
  unpinnedIds,
  cellRefs,
  flipSnap,
  onDrop,
}: UseZoneDragOptions) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [dragPos, setDragPos] = useState({ x: 0, y: 0 })
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [hoverZone, setHoverZone] = useState<Zone | null>(null)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)
  const [activeRect, setActiveRect] = useState<CardRect | null>(null)

  const initCardRects = useRef<CardRect[]>([])
  const pinZoneRef = useRef<HTMLDivElement>(null)
  const unpinZoneRef = useRef<HTMLDivElement>(null)
  const pendingCleanupRef = useRef<(() => void) | null>(null)

  // ── Ref-sync: keep latest values accessible in event handlers
  //    without adding them to useEffect deps ──
  const pinnedRef = useRef(pinnedIds)
  const unpinnedRef = useRef(unpinnedIds)
  const hoverZoneRef = useRef<Zone | null>(null)
  const hoverIdxRef = useRef<number | null>(null)
  const flipSnapRef = useRef(flipSnap)
  const onDropRef = useRef(onDrop)

  pinnedRef.current = pinnedIds
  unpinnedRef.current = unpinnedIds
  hoverZoneRef.current = hoverZone
  hoverIdxRef.current = hoverIdx
  flipSnapRef.current = flipSnap
  onDropRef.current = onDrop

  // Clean up pending listeners on unmount
  useEffect(() => {
    return () => { pendingCleanupRef.current?.() }
  }, [])

  // Snapshot all card positions at drag start
  const measureAll = useCallback(() => {
    const rects: CardRect[] = []
    for (const [id, el] of Object.entries(cellRefs.current)) {
      if (!el) continue
      const r = el.getBoundingClientRect()
      const zone: Zone = pinnedRef.current.includes(id) ? 'pin' : 'unpin'
      rects.push({
        id, x: r.left, y: r.top, w: r.width, h: r.height,
        cx: r.left + r.width / 2, cy: r.top + r.height / 2, zone,
      })
    }
    initCardRects.current = rects
  }, [cellRefs])

  const handlePointerDown = useCallback((e: React.PointerEvent, id: string) => {
    if (e.button !== 0) return
    const el = cellRefs.current[id]
    if (!el) return
    const rect = el.getBoundingClientRect()
    const offset = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    const startX = e.clientX
    const startY = e.clientY
    const zone: Zone = pinnedRef.current.includes(id) ? 'pin' : 'unpin'

    const cardRect: CardRect = {
      id, x: rect.left, y: rect.top, w: rect.width, h: rect.height,
      cx: rect.left + rect.width / 2, cy: rect.top + rect.height / 2, zone,
    }

    const cleanup = () => {
      window.removeEventListener('pointermove', onPendingMove)
      window.removeEventListener('pointerup', onPendingUp)
      pendingCleanupRef.current = null
    }

    const onPendingMove = (ev: PointerEvent) => {
      if (Math.hypot(ev.clientX - startX, ev.clientY - startY) >= DRAG_THRESHOLD) {
        cleanup()
        setDragOffset(offset)
        setDragPos({ x: ev.clientX, y: ev.clientY })
        setActiveId(id)
        measureAll()
        setActiveRect(cardRect)
      }
    }

    const onPendingUp = () => {
      cleanup()
    }

    window.addEventListener('pointermove', onPendingMove)
    window.addEventListener('pointerup', onPendingUp)
    pendingCleanupRef.current = cleanup

    e.preventDefault()
  }, [cellRefs, measureAll])

  // ── Main drag effect ──
  // Only re-runs when activeId changes (drag start / drag end).
  // All other values are read from refs so listeners stay stable.
  useEffect(() => {
    if (!activeId) return

    let rafId: number | null = null

    const onMove = (e: PointerEvent) => {
      // Throttle to one update per animation frame
      if (rafId !== null) cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        rafId = null

        setDragPos({ x: e.clientX, y: e.clientY })
        const cy = e.clientY
        const cx = e.clientX

        const pinRect = pinZoneRef.current?.getBoundingClientRect()
        const unpinRect = unpinZoneRef.current?.getBoundingClientRect()

        // Determine zone from cursor position
        let zone: Zone | null = null
        if (pinRect && cy >= pinRect.top - 40 && cy <= pinRect.bottom + 40) {
          zone = 'pin'
        } else if (unpinRect && cy >= unpinRect.top - 40 && cy <= unpinRect.bottom + 40) {
          zone = 'unpin'
        } else if (pinRect && unpinRect) {
          const pinMid = (pinRect.top + pinRect.bottom) / 2
          const unpinMid = (unpinRect.top + unpinRect.bottom) / 2
          zone = Math.abs(cy - pinMid) < Math.abs(cy - unpinMid) ? 'pin' : 'unpin'
        }

        if (!zone) return

        // Find closest card in target zone
        const zoneCards = initCardRects.current.filter(
          (r) => r.zone === zone && r.id !== activeId,
        )

        if (zoneCards.length === 0) {
          setHoverZone((prev) => {
            if (prev !== zone) flipSnapRef.current()
            return zone
          })
          setHoverIdx(0)
          return
        }

        let closest: CardRect | null = null
        let closestDist = Infinity
        for (const r of zoneCards) {
          const dist = Math.hypot(cx - r.cx, cy - r.cy)
          if (dist < closestDist) {
            closestDist = dist
            closest = r
          }
        }

        if (!closest) return

        const zoneList = zone === 'pin' ? pinnedRef.current : unpinnedRef.current
        const targetIdx = zoneList.indexOf(closest.id)
        const insertIdx = cy < closest.cy ? targetIdx : targetIdx + 1

        setHoverZone((prev) => {
          if (prev !== zone) flipSnapRef.current()
          return zone
        })
        setHoverIdx((prev) => {
          if (prev !== insertIdx) flipSnapRef.current()
          return insertIdx
        })
      })
    }

    const onUp = () => {
      if (rafId !== null) cancelAnimationFrame(rafId)
      const hz = hoverZoneRef.current
      const hi = hoverIdxRef.current
      if (hz !== null) {
        flipSnapRef.current()
        onDropRef.current(activeId, hz, hi ?? 0)
      }
      setActiveId(null)
      setHoverZone(null)
      setHoverIdx(null)
      setActiveRect(null)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [activeId])

  return {
    activeId,
    dragPos,
    dragOffset,
    hoverZone,
    hoverIdx,
    activeRect,
    handlePointerDown,
    pinZoneRef,
    unpinZoneRef,
  }
}
