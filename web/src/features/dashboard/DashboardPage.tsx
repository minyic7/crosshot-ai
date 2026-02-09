import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, GripVertical, Pin, RefreshCw, Clock,
  AlertTriangle, Info, AlertCircle,
} from 'lucide-react'
import { DragDropProvider } from '@dnd-kit/react'
import { useSortable } from '@dnd-kit/react/sortable'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import {
  useGetHealthQuery,
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useRefreshTopicMutation,
  useReorderTopicsMutation,
} from '@/store/api'
import type { Topic, TopicAlert } from '@/types/models'

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

// ─── Helpers ──────────────────────────────────────────────────────

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

function fmtNum(n: number): string {
  if (n >= 100_000) return `${(n / 1000).toFixed(0)}k`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function extractCardMetrics(metrics: Record<string, unknown>): Array<{ label: string; value: string; color?: string }> {
  const out: Array<{ label: string; value: string; color?: string }> = []

  // Posts / contents count
  const posts = metrics.total_posts_analyzed ?? metrics.total_contents
  if (posts != null) out.push({ label: 'Posts', value: fmtNum(Number(posts)) })

  // Dominant sentiment
  const sentiment = metrics.sentiment_distribution as Record<string, number> | undefined
  if (sentiment && typeof sentiment === 'object') {
    const entries = Object.entries(sentiment).sort(([, a], [, b]) => b - a)
    if (entries.length > 0) {
      const [name, pct] = entries[0]
      const color = name === 'bullish' ? 'var(--success)' : name === 'bearish' ? 'var(--error)' : undefined
      out.push({ label: 'Sentiment', value: `${Math.round(pct * 100)}% ${name}`, color })
    }
  }

  // Average views
  const views = metrics.average_views_per_post
  if (views != null) out.push({ label: 'Avg views', value: fmtNum(Number(views)) })

  // Average likes
  const likes = metrics.average_likes_per_post
  if (likes != null && out.length < 3) out.push({ label: 'Avg likes', value: fmtNum(Number(likes)) })

  // Engagement score
  const engagement = metrics.engagement_score ?? metrics.engagement
  if (engagement != null && out.length < 3) out.push({ label: 'Score', value: String(engagement) })

  // Trend velocity
  const velocity = metrics.trend_velocity
  if (velocity != null && out.length < 3) {
    const color = velocity === 'rising' ? 'var(--success)' : velocity === 'falling' ? 'var(--error)' : undefined
    out.push({ label: 'Trend', value: String(velocity), color })
  }

  return out.slice(0, 3)
}

// ─── Topic Card ───────────────────────────────────────────────────

function TopicCard({
  topic,
  index,
  onPin,
  onRefresh,
  onClick,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
}) {
  const { ref, handleRef, isDragging } = useSortable({ id: topic.id, index })
  const alerts = (topic.summary_data?.alerts ?? []).map(normalizeAlert)
  const cardMetrics = topic.summary_data?.metrics ? extractCardMetrics(topic.summary_data.metrics) : []

  return (
    <div
      ref={ref}
      className={`topic-card${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''}${isDragging ? ' dragging' : ''}`}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button, .topic-drag-handle')) return
        onClick(topic.id)
      }}
    >
      {/* Header */}
      <div className="topic-card-header">
        <span ref={handleRef} className="topic-drag-handle"><GripVertical size={14} /></span>
        <span className="topic-card-icon">{topic.icon}</span>
        <h3 className="topic-card-name">{topic.name}</h3>
        <Badge variant={topic.status === 'active' ? 'success' : topic.status === 'paused' ? 'warning' : 'muted'}>
          {topic.status}
        </Badge>
        <div style={{ flex: 1 }} />
        <button
          className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
          onClick={() => onPin(topic.id, !topic.is_pinned)}
          title={topic.is_pinned ? 'Unpin' : 'Pin'}
        >
          <Pin size={13} />
        </button>
      </div>

      {/* Summary */}
      {topic.last_summary ? (
        <p className="topic-card-summary">{topic.last_summary}</p>
      ) : (
        <p className="topic-card-empty">Awaiting first analysis cycle...</p>
      )}

      {/* Metrics mini-grid */}
      {cardMetrics.length > 0 && (
        <div className="topic-metrics-row">
          {cardMetrics.map((m, i) => (
            <div key={i} className="topic-metric-chip">
              <span className="topic-metric-value" style={m.color ? { color: m.color } : undefined}>{m.value}</span>
              <span className="topic-metric-label">{m.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Alert — show top 1 only in card */}
      {alerts.length > 0 && (
        <div className={`topic-card-alert ${alerts[0].level}`}>
          {alerts[0].level === 'critical' ? <AlertCircle size={13} /> : alerts[0].level === 'warning' ? <AlertTriangle size={13} /> : <Info size={13} />}
          <span>{alerts[0].message}</span>
          {alerts.length > 1 && <span className="topic-alert-more">+{alerts.length - 1}</span>}
        </div>
      )}

      {/* Tags */}
      <div className="topic-card-tags">
        {topic.platforms.map((p) => (
          <span key={p} className="topic-tag platform">{p.toUpperCase()}</span>
        ))}
        {topic.keywords.slice(0, 3).map((kw) => (
          <span key={kw} className="topic-tag">{kw}</span>
        ))}
        {topic.keywords.length > 3 && (
          <span className="topic-tag">+{topic.keywords.length - 3}</span>
        )}
      </div>

      {/* Footer */}
      <div className="topic-card-footer">
        <span className="topic-card-time">
          <Clock size={11} />
          {timeAgo(topic.last_crawl_at)}
        </span>
        <button className="topic-card-refresh" onClick={() => onRefresh(topic.id)}>
          <RefreshCw size={11} />
          Refresh
        </button>
      </div>
    </div>
  )
}

// ─── Create Topic Modal ───────────────────────────────────────────

function CreateTopicModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('📊')
  const [description, setDescription] = useState('')
  const [platforms, setPlatforms] = useState<string[]>(['x'])
  const [keywords, setKeywords] = useState('')
  const [interval, setInterval] = useState('6')
  const [createTopic, { isLoading }] = useCreateTopicMutation()

  const handleSubmit = async () => {
    if (!name.trim() || platforms.length === 0) return
    await createTopic({
      name: name.trim(),
      icon,
      description: description.trim() || undefined,
      platforms,
      keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean),
      config: { schedule_interval_hours: Number(interval) || 6 },
    })
    setName('')
    setDescription('')
    setKeywords('')
    setInterval('6')
    onClose()
  }

  const togglePlatform = (p: string) => {
    setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])
  }

  return (
    <Modal open={open} onClose={onClose} title="New Topic" className="create-topic-panel">
      <div className="stack-sm">
        <div className="form-group">
          <label className="form-label">Icon</label>
          <div className="emoji-picker">
            {EMOJI_OPTIONS.map((e) => (
              <button key={e} className={`emoji-option${e === icon ? ' selected' : ''}`} onClick={() => setIcon(e)}>{e}</button>
            ))}
          </div>
        </div>
        <Input label="Name" placeholder="e.g. 马斯克" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="form-group">
          <label className="form-label">Description</label>
          <textarea className="form-input form-textarea" placeholder="Optional description..." value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="form-group">
          <label className="form-label">Platforms</label>
          <div className="flex gap-2">
            {PLATFORM_OPTIONS.map((p) => (
              <button
                key={p}
                style={{
                  padding: '6px 14px', cursor: 'pointer',
                  border: platforms.includes(p) ? '1.5px solid var(--teal)' : '1px solid rgba(100,116,139,0.2)',
                  background: platforms.includes(p) ? 'rgba(82,96,119,0.1)' : 'transparent',
                  borderRadius: '6px', fontWeight: 500,
                }}
                onClick={() => togglePlatform(p)}
              >{p.toUpperCase()}</button>
            ))}
          </div>
        </div>
        <Input label="Keywords (comma-separated)" placeholder="e.g. Elon Musk, SpaceX, Tesla" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <Input label="Refresh Interval (hours)" type="number" min={1} value={interval} onChange={(e) => setInterval(e.target.value)} />
        <Button className="btn-primary" style={{ width: '100%', marginTop: 8 }} disabled={!name.trim() || platforms.length === 0 || isLoading} onClick={handleSubmit}>
          <Plus size={16} />
          {isLoading ? 'Creating...' : 'Create Topic'}
        </Button>
      </div>
    </Modal>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────────

export function DashboardPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)

  const { data: health } = useGetHealthQuery(undefined, { pollingInterval: 10000 })
  const { data: topics, isLoading: topicsLoading } = useListTopicsQuery(undefined, { pollingInterval: 10000 })

  const [updateTopic] = useUpdateTopicMutation()
  const [refreshTopic] = useRefreshTopicMutation()
  const [reorderTopics] = useReorderTopicsMutation()

  const handlePin = useCallback((id: string, pinned: boolean) => { updateTopic({ id, is_pinned: pinned }) }, [updateTopic])
  const handleRefresh = useCallback((id: string) => { refreshTopic(id) }, [refreshTopic])
  const handleTopicClick = useCallback((id: string) => { navigate(`/topic/${id}`) }, [navigate])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleDragEnd = useCallback((event: any) => {
    if (event.canceled || !topics) return
    const { source, target } = event.operation
    if (!source || !target || source.id === target.id) return
    const ids = topics.map((t) => t.id)
    const oldIdx = ids.indexOf(String(source.id))
    const newIdx = ids.indexOf(String(target.id))
    if (oldIdx === -1 || newIdx === -1) return
    const reordered = [...ids]
    const [moved] = reordered.splice(oldIdx, 1)
    reordered.splice(newIdx, 0, moved)
    reorderTopics({ ids: reordered })
  }, [topics, reorderTopics])

  const sortedTopics = topics ?? []

  return (
    <div className="dashboard">
      {/* ── Header ────────────────────────────────── */}
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <Badge variant={health?.status === 'ok' ? 'success' : 'error'}>
          {health?.status === 'ok' ? 'Online' : 'Offline'}
        </Badge>
      </div>

      {/* ── Topics ────────────────────────────────── */}
      <div className="dashboard-topics-header">
        <h2>Topics</h2>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus size={15} />
          New Topic
        </Button>
      </div>

      {topicsLoading ? (
        <div className="topic-grid">
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
        </div>
      ) : sortedTopics.length > 0 ? (
        <DragDropProvider onDragEnd={handleDragEnd}>
          <div className="topic-grid">
            {sortedTopics.map((topic, index) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                index={index}
                onPin={handlePin}
                onRefresh={handleRefresh}
                onClick={handleTopicClick}
              />
            ))}
          </div>
        </DragDropProvider>
      ) : (
        <div className="topic-empty-state">
          <span style={{ fontSize: '2.5rem' }}>📊</span>
          <h3>No topics yet</h3>
          <p>Create your first monitoring topic to get started</p>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={15} />
            Create Topic
          </Button>
        </div>
      )}

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
