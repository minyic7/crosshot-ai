import { useState, useRef, useCallback } from "react"
import { Plus, Pin, PinOff, Clock, ChevronRight, X, TrendingUp, TrendingDown, AlertTriangle, AlertCircle, Info, MessageSquare, GripVertical } from "lucide-react"
import { useApi } from "@/hooks/use-api"

/* ── Types ── */

interface EntryContent {
  label?: string
  value?: string
  change?: string
  direction?: "up" | "down"
  text?: string
  sentiment?: "positive" | "negative" | "neutral"
  keywords?: string[]
  data_points?: { date: string; count: number }[]
  level?: "info" | "warning" | "critical"
  message?: string
  author?: string
}

interface InsightEntry {
  id: number
  topic_id: number
  entry_type: "metric" | "summary" | "trend" | "alert" | "note"
  title: string | null
  content: EntryContent
  source_platform: string | null
  agent_name: string | null
  created_at: string | null
}

interface InsightTopic {
  id: number
  title: string
  description: string | null
  icon: string
  status: string
  is_pinned: number
  display_order: number
  created_by: string
  created_at: string | null
  updated_at: string | null
  entries: InsightEntry[]
}

/* ── Helpers ── */

function timeAgo(iso: string | null): string {
  if (!iso) return "-"
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

async function patchTopic(id: number, body: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await fetch(`/api/insights/topics/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    return res.ok
  } catch {
    return false
  }
}

async function reorderTopics(ids: number[]): Promise<boolean> {
  try {
    const results = await Promise.all(
      ids.map((id, i) =>
        fetch(`/api/insights/topics/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_order: i + 1 }),
        })
      )
    )
    return results.every((r) => r.ok)
  } catch {
    return false
  }
}

/* ── SVG Sparkline ── */

function Sparkline({ points }: { points: { date: string; count: number }[] }) {
  if (!points || points.length < 2) return null
  const values = points.map((p) => p.count)
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min || 1
  const w = 140
  const h = 32
  const pad = 2

  const coords = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  })

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="insight-sparkline">
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke="var(--teal)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={coords[coords.length - 1].split(",")[0]}
        cy={coords[coords.length - 1].split(",")[1]}
        r="2.5"
        fill="var(--teal)"
      />
    </svg>
  )
}

/* ── Entry Renderers ── */

function MetricEntry({ entry }: { entry: InsightEntry }) {
  const c = entry.content
  const isUp = c.direction === "up"
  return (
    <div className="insight-metric">
      <span className="insight-metric-label">{c.label}</span>
      <div className="insight-metric-right">
        <span className="insight-metric-value">{c.value}</span>
        {c.change && (
          <span className={`insight-metric-change ${isUp ? "up" : "down"}`}>
            {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            {c.change}
          </span>
        )}
      </div>
    </div>
  )
}

function SummaryEntry({ entry }: { entry: InsightEntry }) {
  const c = entry.content
  return (
    <div className="insight-summary">
      <span className={`insight-sentiment-dot ${c.sentiment || "neutral"}`} />
      <p>{c.text}</p>
    </div>
  )
}

function TrendEntry({ entry }: { entry: InsightEntry }) {
  const c = entry.content
  return (
    <div className="insight-trend">
      {c.keywords && (
        <div className="insight-keyword-pills">
          {c.keywords.map((kw) => (
            <span key={kw} className="insight-pill">{kw}</span>
          ))}
        </div>
      )}
      {c.data_points && <Sparkline points={c.data_points} />}
    </div>
  )
}

function AlertEntry({ entry }: { entry: InsightEntry }) {
  const c = entry.content
  const level = c.level || "info"
  const Icon = level === "critical" ? AlertTriangle : level === "warning" ? AlertCircle : Info
  return (
    <div className={`insight-alert insight-alert-${level}`}>
      <Icon size={14} />
      <span>{c.message}</span>
    </div>
  )
}

function NoteEntry({ entry }: { entry: InsightEntry }) {
  const c = entry.content
  return (
    <div className="insight-note">
      <MessageSquare size={12} />
      <p>{c.text}</p>
      {c.author && <span className="insight-note-author">— {c.author}</span>}
    </div>
  )
}

function EntryRenderer({ entry }: { entry: InsightEntry }) {
  switch (entry.entry_type) {
    case "metric": return <MetricEntry entry={entry} />
    case "summary": return <SummaryEntry entry={entry} />
    case "trend": return <TrendEntry entry={entry} />
    case "alert": return <AlertEntry entry={entry} />
    case "note": return <NoteEntry entry={entry} />
    default: return null
  }
}

/* ── Topic Card ── */

function TopicCard({
  topic,
  onPin,
  onViewAll,
  onDragStart,
  onDragOver,
  onDragEnd,
  onDrop,
  isDragOver,
}: {
  topic: InsightTopic
  onPin: (id: number, pinned: number) => void
  onViewAll: (topic: InsightTopic) => void
  onDragStart: (e: React.DragEvent, id: number) => void
  onDragOver: (e: React.DragEvent, id: number) => void
  onDragEnd: () => void
  onDrop: (e: React.DragEvent, id: number) => void
  isDragOver: boolean
}) {
  const latestEntry = topic.entries[0]
  const updatedLabel = latestEntry ? timeAgo(latestEntry.created_at) : timeAgo(topic.updated_at)

  return (
    <div
      className={`glass-card insight-card ${topic.is_pinned ? "pinned" : ""} ${topic.status === "paused" ? "paused" : ""} ${isDragOver ? "drag-over" : ""}`}
      draggable
      onDragStart={(e) => onDragStart(e, topic.id)}
      onDragOver={(e) => onDragOver(e, topic.id)}
      onDragEnd={onDragEnd}
      onDrop={(e) => onDrop(e, topic.id)}
    >
      <div className="insight-card-header">
        <div className="insight-card-title-row">
          <span className="insight-drag-handle" aria-label="Drag to reorder">
            <GripVertical size={14} />
          </span>
          <span className="insight-card-icon">{topic.icon}</span>
          <h3>{topic.title}</h3>
          {topic.is_pinned === 1 && <span className="insight-pinned-badge">pinned</span>}
          {topic.status === "paused" && <span className="badge badge-muted">paused</span>}
        </div>
        <button
          className={`insight-pin-btn ${topic.is_pinned ? "active" : ""}`}
          onClick={(e) => {
            e.stopPropagation()
            onPin(topic.id, topic.is_pinned ? 0 : 1)
          }}
          title={topic.is_pinned ? "Unpin" : "Pin to top"}
        >
          {topic.is_pinned ? <PinOff size={14} /> : <Pin size={14} />}
        </button>
      </div>

      <div className="insight-card-body">
        {topic.entries.map((entry) => (
          <EntryRenderer key={entry.id} entry={entry} />
        ))}
        {topic.entries.length === 0 && (
          <p className="text-sm text-muted" style={{ padding: "12px 0", textAlign: "center" }}>
            No insights yet
          </p>
        )}
      </div>

      <div className="insight-card-footer">
        <span className="insight-updated">
          <Clock size={11} />
          {updatedLabel}
        </span>
        <button className="insight-view-all" onClick={() => onViewAll(topic)}>
          View All
          <ChevronRight size={12} />
        </button>
      </div>
    </div>
  )
}

/* ── Detail Modal ── */

function TopicDetailModal({
  topic,
  onClose,
}: {
  topic: InsightTopic
  onClose: () => void
}) {
  const { data: detail } = useApi<{ items: InsightEntry[]; total: number; has_more: boolean }>(
    `/api/insights/topics/${topic.id}/entries?limit=50`
  )
  const entries = detail?.items || topic.entries

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <div className="detail-header">
          <div className="flex items-center gap-3">
            <span style={{ fontSize: "1.5rem" }}>{topic.icon}</span>
            <div>
              <h2>{topic.title}</h2>
              {topic.description && <p className="text-sm text-muted mt-1">{topic.description}</p>}
            </div>
          </div>
          <button className="detail-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="detail-body" style={{ maxHeight: "70vh", overflowY: "auto" }}>
          <div className="insight-detail-entries">
            {entries.map((entry) => (
              <div key={entry.id} className="insight-detail-entry">
                <div className="insight-detail-entry-meta">
                  <span className={`insight-type-badge type-${entry.entry_type}`}>{entry.entry_type}</span>
                  {entry.agent_name && <span className="text-xs text-subtle font-mono">{entry.agent_name}</span>}
                  <span className="text-xs text-subtle">{timeAgo(entry.created_at)}</span>
                </div>
                <EntryRenderer entry={entry} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Create Topic Modal ── */

const EMOJI_OPTIONS = ["📊", "🥇", "👗", "🔍", "🤖", "🔥", "💰", "📈", "🎯", "🌍", "💡", "📱", "🏠", "🎨", "🧬", "⚡"]

function CreateTopicModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [icon, setIcon] = useState("📊")
  const [saving, setSaving] = useState(false)

  const handleCreate = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      const res = await fetch("/api/insights/topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), description: description.trim() || null, icon }),
      })
      if (res.ok) {
        onCreated()
        onClose()
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel create-topic-panel" onClick={(e) => e.stopPropagation()}>
        <div className="detail-header">
          <h2>New Topic</h2>
          <button className="detail-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="detail-body">
          <div className="form-group">
            <label className="form-label">Icon</label>
            <div className="emoji-picker">
              {EMOJI_OPTIONS.map((e) => (
                <button
                  key={e}
                  className={`emoji-option ${icon === e ? "selected" : ""}`}
                  onClick={() => setIcon(e)}
                >
                  {e}
                </button>
              ))}
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Title</label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. 黄金市场分析"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea
              className="form-input form-textarea"
              placeholder="Optional description..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
          <button
            className="btn btn-primary"
            style={{ width: "100%", marginTop: 8 }}
            disabled={!title.trim() || saving}
            onClick={handleCreate}
          >
            {saving ? "Creating..." : "Create Topic"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Skeleton ── */

function TopicCardSkeleton() {
  return (
    <div className="glass-card insight-card">
      <div className="insight-card-header">
        <div className="insight-card-title-row">
          <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 8 }} />
          <div className="skeleton skeleton-text" style={{ width: "60%" }} />
        </div>
      </div>
      <div className="insight-card-body">
        <div className="skeleton skeleton-text" style={{ width: "80%" }} />
        <div className="skeleton skeleton-text" style={{ width: "50%", marginTop: 8 }} />
        <div className="skeleton skeleton-text" style={{ width: "70%", marginTop: 8 }} />
      </div>
    </div>
  )
}

/* ── Main Dashboard ── */

export function Dashboard() {
  const { data: serverTopics, loading, refetch } = useApi<InsightTopic[]>("/api/insights/topics")
  const [localTopics, setLocalTopics] = useState<InsightTopic[] | null>(null)
  const [detailTopic, setDetailTopic] = useState<InsightTopic | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const dragItemId = useRef<number | null>(null)
  const [dragOverId, setDragOverId] = useState<number | null>(null)

  // Use localTopics for optimistic updates, fall back to serverTopics
  const topics = localTopics ?? serverTopics

  // Sync server data when it arrives (only if no local override)
  const lastServerRef = useRef(serverTopics)
  if (serverTopics !== lastServerRef.current) {
    lastServerRef.current = serverTopics
    setLocalTopics(null) // Reset optimistic state when server data refreshes
  }

  const sortTopics = useCallback((list: InsightTopic[]): InsightTopic[] => {
    return [...list].sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return b.is_pinned - a.is_pinned
      return a.display_order - b.display_order
    })
  }, [])

  const handlePin = useCallback(async (id: number, pinned: number) => {
    if (!topics) return
    // Optimistic update
    const updated = topics.map((t) => t.id === id ? { ...t, is_pinned: pinned } : t)
    setLocalTopics(sortTopics(updated))
    // Persist
    const ok = await patchTopic(id, { is_pinned: pinned })
    if (!ok) {
      // Revert on failure
      setLocalTopics(null)
    } else {
      refetch()
    }
  }, [topics, sortTopics, refetch])

  /* ── Drag & Drop ── */

  const handleDragStart = useCallback((e: React.DragEvent, id: number) => {
    dragItemId.current = id
    e.dataTransfer.effectAllowed = "move"
    // Make the drag image slightly transparent
    const el = e.currentTarget as HTMLElement
    el.style.opacity = "0.5"
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent, id: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    if (dragItemId.current !== id) {
      setDragOverId(id)
    }
  }, [])

  const handleDragEnd = useCallback(() => {
    dragItemId.current = null
    setDragOverId(null)
    // Restore opacity on all cards
    document.querySelectorAll(".insight-card").forEach((el) => {
      (el as HTMLElement).style.opacity = ""
    })
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent, targetId: number) => {
    e.preventDefault()
    const sourceId = dragItemId.current
    if (!sourceId || sourceId === targetId || !topics) return

    // Compute new order by swapping positions
    const sourceIdx = topics.findIndex((t) => t.id === sourceId)
    const targetIdx = topics.findIndex((t) => t.id === targetId)
    if (sourceIdx === -1 || targetIdx === -1) return

    const reordered = [...topics]
    const [moved] = reordered.splice(sourceIdx, 1)
    reordered.splice(targetIdx, 0, moved)

    // Assign new display_order values
    const withNewOrder = reordered.map((t, i) => ({ ...t, display_order: i + 1 }))

    // Optimistic update
    setLocalTopics(sortTopics(withNewOrder))
    setDragOverId(null)
    dragItemId.current = null

    // Persist all new orders
    const ok = await reorderTopics(withNewOrder.map((t) => t.id))
    if (!ok) {
      setLocalTopics(null)
    } else {
      refetch()
    }
  }, [topics, sortTopics, refetch])

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="mt-2 text-base text-muted">
            Insight board — topics tracked by your agents
          </p>
        </div>
        <button className="topnav-cta" onClick={() => setShowCreate(true)}>
          <Plus size={14} />
          New Topic
        </button>
      </div>

      {/* Content */}
      {loading && !topics ? (
        <div className="insight-grid">
          <TopicCardSkeleton />
          <TopicCardSkeleton />
          <TopicCardSkeleton />
          <TopicCardSkeleton />
        </div>
      ) : !topics || topics.length === 0 ? (
        <div className="glass-card insight-empty">
          <p className="text-muted">No topics yet. Create one to get started.</p>
          <button className="btn btn-outline" style={{ marginTop: 12 }} onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            Create Topic
          </button>
        </div>
      ) : (
        <>
          {/* Pinned Section */}
          {topics.some((t) => t.is_pinned) && (
            <div className="insight-section">
              <div className="insight-section-header">
                <Pin size={14} />
                <span>Pinned</span>
              </div>
              <div className="insight-grid">
                {topics.filter((t) => t.is_pinned).map((topic) => (
                  <TopicCard
                    key={topic.id}
                    topic={topic}
                    onPin={handlePin}
                    onViewAll={setDetailTopic}
                    onDragStart={handleDragStart}
                    onDragOver={handleDragOver}
                    onDragEnd={handleDragEnd}
                    onDrop={handleDrop}
                    isDragOver={dragOverId === topic.id}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Unpinned Section */}
          {topics.some((t) => !t.is_pinned) && (
            <div className="insight-section">
              {topics.some((t) => t.is_pinned) && (
                <div className="insight-section-header">
                  <span>All Topics</span>
                </div>
              )}
              <div className="insight-grid">
                {topics.filter((t) => !t.is_pinned).map((topic) => (
                  <TopicCard
                    key={topic.id}
                    topic={topic}
                    onPin={handlePin}
                    onViewAll={setDetailTopic}
                    onDragStart={handleDragStart}
                    onDragOver={handleDragOver}
                    onDragEnd={handleDragEnd}
                    onDrop={handleDrop}
                    isDragOver={dragOverId === topic.id}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Modals */}
      {detailTopic && (
        <TopicDetailModal topic={detailTopic} onClose={() => setDetailTopic(null)} />
      )}
      {showCreate && (
        <CreateTopicModal onClose={() => setShowCreate(false)} onCreated={refetch} />
      )}
    </div>
  )
}
