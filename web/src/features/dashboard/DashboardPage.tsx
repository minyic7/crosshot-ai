import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DndContext,
  DragOverlay,
  defaultDropAnimationSideEffects,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  closestCenter,
  useDroppable,
  type DragStartEvent,
  type DragOverEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  arrayMove,
  rectSortingStrategy,
  defaultAnimateLayoutChanges,
  type AnimateLayoutChanges,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Plus, Pin, RefreshCw, GripVertical,
  AlertTriangle, Trash2,
  Sparkles, Loader2,
  Pencil, Users,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
import {
  useListTopicsQuery,
  useUpdateTopicMutation,
  useReanalyzeTopicMutation,
  useReorderTopicsMutation,
  useListUsersQuery,
  useUpdateUserMutation,
  useReanalyzeUserMutation,
  useReorderUsersMutation,
  useResetAllDataMutation,
} from '@/store/api'
import type { Topic, TopicAlert, TopicPipeline, User as UserType, TopicStatus } from '@/types/models'
import { CreateEditModal } from './CreateEditModal'

// ─── Custom Sensor (ignores buttons) ────────────────────────

class SmartMouseSensor extends MouseSensor {
  static activators = [
    {
      eventName: 'onMouseDown' as const,
      handler: ({ nativeEvent: e }: { nativeEvent: MouseEvent }) => {
        return e.button === 0 && !(e.target as HTMLElement).closest('button, [data-no-dnd]')
      },
    },
  ]
}

// ─── Helpers ──────────────────────────────────────────────────

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function normalizeAlert(alert: TopicAlert): { level: string; message: string } {
  if (typeof alert === 'string') return { level: 'info', message: alert }
  return alert
}

function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^>\s+/gm, '')
    .replace(/\n{2,}/g, ' ')
    .replace(/\n/g, ' ')
    .trim()
}

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}m`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

// ─── Pipeline Badge ──────────────────────────────────────────

function PipelineBadge({ pipeline }: { pipeline: TopicPipeline }) {
  const { phase, total, done } = pipeline

  if (phase === 'analyzing') {
    return (
      <div className="pipeline-badge analyzing">
        <Loader2 size={12} className="pipeline-spin" />
        <span>Analyzing topic data...</span>
      </div>
    )
  }

  if (phase === 'crawling') {
    const t = Number(total) || 0
    const d = Number(done) || 0
    const pct = t > 0 ? Math.round((d / t) * 100) : 0
    return (
      <div className="pipeline-badge crawling">
        <RefreshCw size={12} className="pipeline-spin" />
        <span>Crawling {d}/{t}</span>
        <div className="pipeline-bar">
          <div className="pipeline-bar-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
    )
  }

  if (phase === 'summarizing') {
    return (
      <div className="pipeline-badge summarizing">
        <Sparkles size={12} className="pipeline-spin" />
        <span>Analyzing data...</span>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="pipeline-badge error">
        <AlertTriangle size={12} />
        <span>{pipeline.error_msg || 'Pipeline error'}</span>
      </div>
    )
  }

  return null
}

// ─── Topic Card ───────────────────────────────────────────────

function TopicCard({
  topic,
  index,
  onPin,
  onRefresh,
  onEdit,
  onClick,
  refreshing,
  dragListeners,
  className = '',
  style,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onEdit: (id: string) => void
  onClick: (id: string) => void
  refreshing?: boolean
  dragListeners?: Record<string, unknown>
  className?: string
  style?: React.CSSProperties
}) {
  const navigate = useNavigate()
  const alerts = (topic.summary_data?.alerts ?? []).map(normalizeAlert)
  const d = index * 80
  const [risen, setRisen] = useState(false)

  return (
    <div
      className={`topic-card${risen ? '' : ' rise'}${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''}${topic.type === 'user' ? ' user-card' : ''} ${className}`}
      style={{ animationDelay: risen ? undefined : `${180 + d}ms`, ...style }}
      onAnimationEnd={(e) => { if (e.animationName === 'rise') setRisen(true) }}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button, .topic-drag-handle')) return
        onClick(topic.id)
      }}
    >
      <div className="topic-card-shimmer" />

      {/* Drag handle */}
      <div className="topic-drag-handle" {...dragListeners}>
        <GripVertical size={14} />
      </div>

      {/* Pin button — independent of actions so no flash on hover-out */}
      <button
        className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
        onClick={() => onPin(topic.id, !topic.is_pinned)}
        title={topic.is_pinned ? 'Unpin' : 'Pin'}
      >
        <Pin size={12} />
      </button>

      {/* Hover actions — float top-right */}
      <div className="topic-card-actions">
        <button
          className="topic-card-refresh"
          onClick={() => onEdit(topic.id)}
          title="Edit"
        >
          <Pencil size={10} />
        </button>
        <button
          className="topic-card-refresh"
          onClick={() => onRefresh(topic.id)}
          disabled={refreshing}
        >
          <RefreshCw size={10} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* HEADER */}
      <div className="topic-card-row1">
        <div className="topic-card-icon-box">{topic.type === 'user' ? '👤' : topic.icon}</div>
        <h3 className="topic-card-name">{topic.name}</h3>
        {topic.type === 'user' && <span className="topic-tag platform" style={{ fontSize: '0.6rem', marginLeft: 4 }}>{topic.platforms[0]?.toUpperCase()}</span>}
        <span className={`topic-status-pill ${topic.status}`}>
          <span className="topic-status-pill-dot" />
          {topic.status === 'active' ? 'Live' : 'Paused'}
        </span>
      </div>

      <div className="topic-card-subtitle">
        {timeAgo(topic.last_crawl_at)}
        <span className="meta-sep">&middot;</span>
        {fmtNum(topic.total_contents)} posts
      </div>

      {/* Pipeline progress */}
      {topic.pipeline && <PipelineBadge pipeline={topic.pipeline} />}

      {/* MIDDLE — description + future per-topic widget slot */}
      <div className="topic-card-middle">
        {alerts.length > 0 ? (
          <p className="topic-card-summary">
            <span className="topic-card-alert-icon">
              {alerts[0].level === 'critical' ? '🔴' : alerts[0].level === 'warning' ? '⚠️' : 'ℹ️'}
            </span>
            {topic.last_summary ? stripMarkdown(topic.last_summary) : alerts[0].message}
          </p>
        ) : topic.last_summary ? (
          <p className="topic-card-summary">{stripMarkdown(topic.last_summary)}</p>
        ) : !topic.pipeline ? (
          <p className="topic-card-empty">Awaiting first analysis cycle...</p>
        ) : null}
      </div>

      {/* FOOTER */}
      <div className="topic-card-footer">
        <div className="topic-card-sources">
          {topic.platforms.map((p) => (
            <span key={p} className="topic-source-icon" title={p.toUpperCase()}>
              {p === 'x' ? (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              )}
            </span>
          ))}
        </div>
        <div className="topic-card-tags">
          {topic.type === 'user' && topic.description ? (
            <span className="topic-tag">@{topic.description}</span>
          ) : (
            <>
              {topic.keywords.slice(0, 2).map((kw) => (
                <span key={kw} className="topic-tag">#{kw}</span>
              ))}
              {topic.keywords.length > 2 && (
                <span className="topic-tag-more">+{topic.keywords.length - 2}</span>
              )}
            </>
          )}
          {topic.type === 'user' && (topic.users ?? []).length > 0 && (
            <div className="topic-card-avatars">
              {topic.users!.slice(0, 3).map((u) => (
                <button
                  key={u.id}
                  className="topic-card-avatar topic-card-avatar--topic"
                  title={u.name}
                  onClick={(e) => { e.stopPropagation(); navigate(`/topic/${u.id}`) }}
                >
                  {u.profile_url || '📊'}
                </button>
              ))}
              {topic.users!.length > 3 && (
                <span className="topic-card-avatar-more">+{topic.users!.length - 3}</span>
              )}
            </div>
          )}
          {topic.type !== 'user' && (topic.users ?? []).length > 0 && (
            <div className="topic-card-avatars">
              {topic.users!.slice(0, 3).map((u) => (
                <button
                  key={u.id}
                  className="topic-card-avatar"
                  title={u.username ? `@${u.username}` : u.name}
                  onClick={(e) => { e.stopPropagation(); navigate(`/user/${u.id}`) }}
                >
                  {(u.username || u.name || '?')[0].toUpperCase()}
                </button>
              ))}
              {topic.users!.length > 3 && (
                <span className="topic-card-avatar-more">+{topic.users!.length - 3}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Sortable Card Wrapper ──────────────────────────────────

function SortableCard({
  topic,
  index,
  onPin,
  onRefresh,
  onEdit,
  onClick,
  refreshing,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onEdit: (id: string) => void
  onClick: (id: string) => void
  refreshing?: boolean
}) {
  const skipPostDrop: AnimateLayoutChanges = (args) =>
    args.active ? defaultAnimateLayoutChanges(args) : false

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: topic.id, animateLayoutChanges: skipPostDrop })

  // On the frame isDragging flips false → card becomes visible.
  // Force transform=0, transition=none so it appears at its DOM position
  // instantly, avoiding a flash from stale drag offsets.
  const wasDragging = useRef(false)
  const justDropped = wasDragging.current && !isDragging
  wasDragging.current = isDragging

  const style: React.CSSProperties = {
    transform: (isDragging || justDropped) ? 'translate3d(0, 0, 0)' : (transform ? CSS.Transform.toString(transform) : 'translate3d(0, 0, 0)'),
    transition: justDropped ? 'none' : transition,
    opacity: isDragging ? 0 : 1,
  }

  return (
    <div ref={setNodeRef} className="g-cell" style={style} {...attributes}>
      <TopicCard
        topic={topic}
        index={index}
        onPin={onPin}
        onRefresh={onRefresh}
        onEdit={onEdit}
        onClick={onClick}
        refreshing={refreshing}
        dragListeners={listeners}
      />
    </div>
  )
}

// ─── Zone Grid ────────────────────────────────────────────────

function ZoneGrid({
  zone,
  title,
  icon,
  items,
  activeId,
  crossingZone,
  currentDragZone,
  onPin,
  onRefresh,
  onEdit,
  onClick,
  refreshingIds,
}: {
  zone: 'pinned' | 'unpinned'
  title: string
  icon: string
  items: Topic[]
  activeId: string | null
  crossingZone: boolean
  currentDragZone: string | null
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onEdit: (id: string) => void
  onClick: (id: string) => void
  refreshingIds: Set<string>
}) {
  const { setNodeRef } = useDroppable({ id: `zone-${zone}` })

  const glowClass = crossingZone && currentDragZone === zone
    ? zone === 'pinned' ? 'zone-glow-pin' : 'zone-glow-unpin'
    : ''

  return (
    <div
      ref={setNodeRef}
      className={`zone ${activeId ? 'zone-active' : ''} ${glowClass}`}
    >
      <div className="zone-hd">
        <span className="zone-icon">{icon}</span>
        <span className="zone-title">{title}</span>
        <span className="zone-ct">{items.length}</span>
        {crossingZone && currentDragZone === zone && (
          <span className="zone-hint">
            {zone === 'pinned' ? 'Drop to pin' : 'Drop to unpin'}
          </span>
        )}
      </div>

      {items.length === 0 && !activeId && zone === 'pinned' && (
        <div className="zone-empty">Drag topics here to pin them</div>
      )}
      {items.length === 0 && activeId && zone === 'pinned' && (
        <div className="zone-drop-target">
          <div className="zone-drop-inner">Drop here to pin</div>
        </div>
      )}

      <SortableContext items={items.map((t) => t.id)} strategy={rectSortingStrategy}>
        <div className="zone-grid">
          {items.map((topic, i) => (
            <SortableCard
              key={topic.id}
              topic={topic}
              index={i}
              onPin={onPin}
              onRefresh={onRefresh}
              onEdit={onEdit}
              onClick={onClick}
              refreshing={refreshingIds.has(topic.id)}
            />
          ))}
        </div>
      </SortableContext>
    </div>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────


export function DashboardPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [editEntity, setEditEntity] = useState<Topic | UserType | null>(null)
  const [filter, setFilter] = useState<'All' | 'Active' | 'Paused'>('All')
  const [showUsers, setShowUsers] = useState(true)

  // Sliding indicator for filter pills
  const pillsRef = useRef<HTMLDivElement>(null)
  const [slider, setSlider] = useState({ left: 0, width: 0, ready: false })
  useEffect(() => {
    if (!pillsRef.current) return
    const btn = pillsRef.current.querySelector('.filter-pill-active') as HTMLElement | null
    if (btn) setSlider({ left: btn.offsetLeft, width: btn.offsetWidth, ready: true })
  }, [filter])

  // Poll faster when any entity has an active pipeline
  const [pollingInterval, setPollingInterval] = useState(30_000)
  const { data: topics, isLoading: topicsLoading } = useListTopicsQuery(undefined, { pollingInterval })
  const { data: allUsers, isLoading: usersLoading } = useListUsersQuery(undefined, { pollingInterval })

  useEffect(() => {
    const hasActivePipeline = topics?.some((t) => t.pipeline && t.pipeline.phase !== 'done')
      || allUsers?.some((u) => u.pipeline && u.pipeline.phase !== 'done')
    setPollingInterval(hasActivePipeline ? 3_000 : 30_000)
  }, [topics, allUsers])

  const [updateTopic] = useUpdateTopicMutation()
  const [updateUser] = useUpdateUserMutation()
  const [reanalyzeTopic] = useReanalyzeTopicMutation()
  const [reanalyzeUser] = useReanalyzeUserMutation()
  const [reorderTopics] = useReorderTopicsMutation()
  const [reorderUsers] = useReorderUsersMutation()
  const [resetAllData, { isLoading: isResetting }] = useResetAllDataMutation()
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [refreshingIds, setRefreshingIds] = useState<Set<string>>(new Set())

  // Clear refreshingIds when pipeline finishes
  useEffect(() => {
    if (!topics && !allUsers) return
    setRefreshingIds(prev => {
      const next = new Set(prev)
      for (const id of prev) {
        const t = allTopicsRef.current.find(x => x.id === id)
        const phase = t?.pipeline?.phase
        if (!phase || phase === 'done' || phase === 'error') next.delete(id)
      }
      return next.size === prev.size ? prev : next
    })
  }, [topics, allUsers])

  const handleRefresh = useCallback((id: string) => {
    setRefreshingIds(prev => new Set(prev).add(id))
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (item?.type === 'user') reanalyzeUser(id)
    else reanalyzeTopic(id)
  }, [reanalyzeTopic, reanalyzeUser])
  const handleTopicClick = useCallback((id: string) => {
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (item?.type === 'user') navigate(`/user/${id}`)
    else navigate(`/topic/${id}`)
  }, [navigate])
  const handleEdit = useCallback((id: string) => {
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (!item) return
    if (item.type === 'user') {
      // Convert back from Topic-like to UserType for the modal
      const u = allUsers?.find((u) => u.id === id)
      if (u) setEditEntity(u)
    } else {
      setEditEntity(item)
    }
  }, [allUsers])

  // Map users to Topic-like objects for the shared grid
  const userAsTopic = useCallback((u: UserType): Topic => ({
    id: u.id,
    type: 'user',
    name: u.name,
    icon: '👤',
    description: u.username, // store username in description for card display
    platforms: [u.platform],
    keywords: [],
    config: u.config,
    status: u.status as TopicStatus,
    is_pinned: u.is_pinned,
    position: u.position,
    total_contents: u.total_contents,
    last_crawl_at: u.last_crawl_at,
    last_summary: u.last_summary,
    summary_data: u.summary_data,
    pipeline: u.pipeline,
    created_at: u.created_at,
    updated_at: u.updated_at,
    users: u.topics?.map(t => ({ id: t.id, name: t.name, platform: '', username: null, profile_url: t.icon || '📊' })), // carry bound topics via users field; icon stored in profile_url
  }), [])

  // Merge topics + users (only when toggle is on)
  const allTopics = useMemo(() => {
    const t = topics ?? []
    if (!showUsers) return t
    const u = (allUsers ?? []).map(userAsTopic)
    return [...t, ...u]
  }, [topics, allUsers, userAsTopic, showUsers])
  const allTopicsRef = useRef(allTopics)
  allTopicsRef.current = allTopics
  const filtered = filter === 'All' ? allTopics : filter === 'Active' ? allTopics.filter((t) => t.status === 'active') : allTopics.filter((t) => t.status === 'paused')
  const pinned = useMemo(() => filtered.filter((t) => t.is_pinned), [filtered])
  const unpinned = useMemo(() => filtered.filter((t) => !t.is_pinned), [filtered])

  // ── DnD local state ──
  const [activeId, setActiveId] = useState<string | null>(null)
  const [containers, setContainers] = useState<{ pinned: string[]; unpinned: string[] }>({ pinned: [], unpinned: [] })
  const containersRef = useRef(containers)
  containersRef.current = containers
  const skipSyncRef = useRef(false)

  // Sync from server when not dragging (skip one cycle after drop
  // so the local reorder isn't overwritten by stale server data)
  const pinnedKey = useMemo(() => pinned.map((t) => t.id).join(','), [pinned])
  const unpinnedKey = useMemo(() => unpinned.map((t) => t.id).join(','), [unpinned])

  useEffect(() => {
    if (activeId) return
    if (skipSyncRef.current) { skipSyncRef.current = false; return }
    setContainers({
      pinned: pinnedKey ? pinnedKey.split(',') : [],
      unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
    })
  }, [pinnedKey, unpinnedKey, activeId])

  // Build display lists from local container state
  const topicMap = useMemo(() => {
    const map = new Map<string, Topic>()
    allTopics.forEach((t) => map.set(t.id, t))
    return map
  }, [allTopics])

  const displayPinned = useMemo(
    () => containers.pinned.map((id) => topicMap.get(id)).filter((t): t is Topic => !!t),
    [containers.pinned, topicMap],
  )
  const displayUnpinned = useMemo(
    () => containers.unpinned.map((id) => topicMap.get(id)).filter((t): t is Topic => !!t),
    [containers.unpinned, topicMap],
  )

  // DnD sensors
  const sensors = useSensors(
    useSensor(SmartMouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
  )

  const findContainer = useCallback((id: string): 'pinned' | 'unpinned' | null => {
    if (containersRef.current.pinned.includes(id)) return 'pinned'
    if (containersRef.current.unpinned.includes(id)) return 'unpinned'
    return null
  }, [])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }, [])

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event
    if (!over || over.id === active.id) return

    const activeContainer = findContainer(active.id as string)
    let overContainer = findContainer(over.id as string)
    if (!overContainer) {
      if (over.id === 'zone-pinned') overContainer = 'pinned'
      else if (over.id === 'zone-unpinned') overContainer = 'unpinned'
    }

    if (!activeContainer || !overContainer) return

    if (activeContainer === overContainer) {
      // Same-container: reorder DOM in real-time so drop has no flash
      setContainers((prev) => {
        const items = [...prev[activeContainer]]
        const oldIndex = items.indexOf(active.id as string)
        const newIndex = items.indexOf(over.id as string)
        if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return prev
        return { ...prev, [activeContainer]: arrayMove(items, oldIndex, newIndex) }
      })
    } else {
      // Cross-container: move item between zones
      setContainers((prev) => {
        const from = [...prev[activeContainer]]
        const to = [...prev[overContainer!]]
        const activeIndex = from.indexOf(active.id as string)
        if (activeIndex === -1) return prev
        from.splice(activeIndex, 1)
        const overIndex = to.indexOf(over.id as string)
        to.splice(overIndex >= 0 ? overIndex : to.length, 0, active.id as string)
        return { ...prev, [activeContainer]: from, [overContainer!]: to }
      })
    }
  }, [findContainer])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { over } = event

    if (!over) {
      setActiveId(null)
      setContainers({
        pinned: pinnedKey ? pinnedKey.split(',') : [],
        unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
      })
      return
    }

    // DOM order already matches visual order (updated in handleDragOver),
    // just finalize: clear active and persist to backend.
    // Skip the next sync so stale server data doesn't overwrite our local order.
    skipSyncRef.current = true
    setActiveId(null)

    // Split IDs by type — topics and users have separate reorder APIs
    const isUserItem = (id: string) => allTopicsRef.current.find(t => t.id === id)?.type === 'user'
    const { pinned, unpinned } = containersRef.current
    const topicPinned = pinned.filter(id => !isUserItem(id))
    const topicUnpinned = unpinned.filter(id => !isUserItem(id))
    const userPinned = pinned.filter(id => isUserItem(id))
    const userUnpinned = unpinned.filter(id => isUserItem(id))

    if (topicPinned.length > 0 || topicUnpinned.length > 0) {
      reorderTopics({ pinned: topicPinned, unpinned: topicUnpinned })
    }
    if (userPinned.length > 0 || userUnpinned.length > 0) {
      reorderUsers({ pinned: userPinned, unpinned: userUnpinned })
    }
  }, [reorderTopics, reorderUsers, pinnedKey, unpinnedKey])

  const handleDragCancel = useCallback(() => {
    setActiveId(null)
    setContainers({
      pinned: pinnedKey ? pinnedKey.split(',') : [],
      unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
    })
  }, [pinnedKey, unpinnedKey])

  // Derived drag state for visual effects
  const activeTopic = activeId ? topicMap.get(activeId) ?? null : null
  const originalZone = activeTopic?.is_pinned ? 'pinned' : 'unpinned'
  const currentDragZone = activeId ? findContainer(activeId) : null
  const crossingZone = !!(activeId && currentDragZone && currentDragZone !== originalZone)

  // Pin via button — route to correct mutation based on type
  const handlePin = useCallback((id: string, pinned: boolean) => {
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (item?.type === 'user') updateUser({ id, is_pinned: pinned })
    else updateTopic({ id, is_pinned: pinned })
  }, [updateTopic, updateUser])

  const totalPosts = allTopics.reduce((s, t) => s + t.total_contents, 0)

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header rise">
        <div>
          <p className="dashboard-subtitle">
            Tracking {allTopics.length} topics · {totalPosts} posts collected
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ghost-danger"
            onClick={() => setShowResetConfirm(true)}
            title="Clear all data"
          >
            <Trash2 size={15} />
          </button>
          <button className="btn-accent" onClick={() => setShowCreate(true)}>
            <Plus size={15} />
            New
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="dashboard-filter-bar rise" style={{ animationDelay: '100ms' }}>
        <div className="filter-pills" ref={pillsRef}>
          <div
            className="filter-pill-slider"
            style={{ left: slider.left, width: slider.width, opacity: slider.ready ? 1 : 0 }}
          />
          {([
            { key: 'All' as const, count: allTopics.length },
            { key: 'Active' as const, count: allTopics.filter(t => t.status === 'active').length },
            { key: 'Paused' as const, count: allTopics.filter(t => t.status !== 'active').length },
          ]).map((f) => (
            <button
              key={f.key}
              className={`filter-pill${filter === f.key ? ' filter-pill-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.key}
              <span className="filter-pill-count">{f.count}</span>
            </button>
          ))}
        </div>
        {(allUsers?.length ?? 0) > 0 && (
          <button
            className={`user-toggle${showUsers ? ' active' : ''}`}
            onClick={() => setShowUsers(v => !v)}
            title={showUsers ? 'Hide user cards' : 'Show user cards'}
          >
            <Users size={13} />
            Users
            <span className="filter-pill-count">{allUsers!.length}</span>
          </button>
        )}
      </div>

      {/* Topic zones */}
      {(topicsLoading || usersLoading) ? (
        <div className="topic-grid">
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          {/* Pinned Zone */}
          <ZoneGrid
            zone="pinned"
            title="Pinned"
            icon="📌"
            items={displayPinned}
            activeId={activeId}
            crossingZone={crossingZone}
            currentDragZone={currentDragZone}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onEdit={handleEdit}
            onClick={handleTopicClick}
            refreshingIds={refreshingIds}
          />

          {/* All Topics Zone */}
          <ZoneGrid
            zone="unpinned"
            title="All Topics"
            icon="📋"
            items={displayUnpinned}
            activeId={activeId}
            crossingZone={crossingZone}
            currentDragZone={currentDragZone}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onEdit={handleEdit}
            onClick={handleTopicClick}
            refreshingIds={refreshingIds}
          />

          {/* Empty state */}
          {displayPinned.length === 0 && displayUnpinned.length === 0 && !activeId && (
            <div className="topic-empty-state pop">
              <span style={{ fontSize: '2.5rem' }}>📊</span>
              <h3>No {filter.toLowerCase()} topics found</h3>
              <p>Create your first topic or user to get started</p>
              <button className="btn-accent" onClick={() => setShowCreate(true)}>
                <Plus size={15} />
                Create
              </button>
            </div>
          )}

          <DragOverlay dropAnimation={{
            duration: 180,
            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
            sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0' } } }),
          }}>
            {activeTopic && (
              <TopicCard
                topic={{ ...activeTopic, is_pinned: currentDragZone === 'pinned' }}
                index={0}
                onPin={() => {}}
                onRefresh={() => {}}
                onEdit={() => {}}
                onClick={() => {}}
                className={`drag-flying ${crossingZone ? 'cross-zone' : ''}`}
              />
            )}
          </DragOverlay>
        </DndContext>
      )}

      {/* FAB: mobile-only "New Topic" button — hidden when modal is open */}
      {!showCreate && (
        <button className="fab" onClick={() => setShowCreate(true)} aria-label="New Topic">
          <Plus size={24} />
        </button>
      )}

      <CreateEditModal open={showCreate} onClose={() => setShowCreate(false)} />
      <CreateEditModal open={!!editEntity} onClose={() => setEditEntity(null)} editEntity={editEntity} />

      {/* Reset confirmation modal */}
      <Modal open={showResetConfirm} onClose={() => setShowResetConfirm(false)} title="Clear All Data">
        <div className="stack" style={{ gap: 16 }}>
          <p className="text-sm" style={{ color: 'var(--ink-3)' }}>
            This will permanently delete all topics, users, contents, and tasks.
            This action cannot be undone.
          </p>
          <div className="flex justify-end gap-2">
            <button
              className="btn-ghost"
              onClick={() => setShowResetConfirm(false)}
              disabled={isResetting}
            >
              Cancel
            </button>
            <button
              className="btn-danger"
              disabled={isResetting}
              onClick={async () => {
                await resetAllData()
                setShowResetConfirm(false)
              }}
            >
              {isResetting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {isResetting ? 'Clearing...' : 'Clear Everything'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
