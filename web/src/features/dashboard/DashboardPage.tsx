import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, GripVertical, Pin, RefreshCw,
  AlertTriangle, Info, AlertCircle,
} from 'lucide-react'
import { DragDropProvider } from '@dnd-kit/react'
import { useSortable } from '@dnd-kit/react/sortable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import {
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useRefreshTopicMutation,
  useReorderTopicsMutation,
} from '@/store/api'
import type { Topic, TopicAlert } from '@/types/models'

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

// ─── Animated Number ──────────────────────────────────────────

function AnimatedNum({ to, dur = 950 }: { to: number; dur?: number }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const s = performance.now()
    const go = (n: number) => {
      const p = Math.min((n - s) / dur, 1)
      setV(Math.round((1 - Math.pow(1 - p, 4)) * to))
      if (p < 1) requestAnimationFrame(go)
    }
    requestAnimationFrame(go)
  }, [to, dur])
  return <>{v}</>
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

function fmtNum(n: number): string {
  if (n >= 100_000) return `${(n / 1000).toFixed(0)}k`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

interface CardMetric {
  label: string
  value: string | number
  color?: string
  sub?: string
  subColor?: string
  subBg?: string
  animate?: boolean
}

function extractCardMetrics(metrics: Record<string, unknown>): CardMetric[] {
  const out: CardMetric[] = []

  // Posts count
  const posts = metrics.total_contents
  if (posts != null) out.push({ label: 'Posts', value: Number(posts), animate: true })

  // Total engagement (likes + retweets + replies)
  const likes = Number(metrics.total_likes ?? 0)
  const retweets = Number(metrics.total_retweets ?? 0)
  const replies = Number(metrics.total_replies ?? 0)
  const totalEngagement = likes + retweets + replies
  if (totalEngagement > 0) out.push({ label: 'Engagement', value: fmtNum(totalEngagement), color: 'var(--accent)' })

  // Total views
  const views = metrics.total_views
  if (views != null && Number(views) > 0) out.push({ label: 'Views', value: fmtNum(Number(views)) })

  // Media percentage
  const mediaPct = metrics.with_media_pct
  if (mediaPct != null && out.length < 4) out.push({ label: 'Media', value: `${mediaPct}%` })

  // Top author fallback
  const topAuthor = metrics.top_author as string | undefined
  if (topAuthor && out.length < 4) out.push({ label: 'Top Author', value: `@${topAuthor}` })

  return out.slice(0, 4)
}

// ─── Topic Card ───────────────────────────────────────────────

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
  const d = index * 110

  return (
    <div
      ref={ref}
      className={`topic-card rise${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''}${isDragging ? ' dragging' : ''}`}
      style={{ animationDelay: `${220 + d}ms` }}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button, .topic-drag-handle, .topic-card-refresh')) return
        onClick(topic.id)
      }}
    >
      <div className="topic-card-shimmer" />

      {/* Header */}
      <div className="topic-card-header">
        <div className="topic-card-title-area">
          <span ref={handleRef} className="topic-drag-handle"><GripVertical size={14} /></span>
          <div className="topic-card-icon-box">{topic.icon}</div>
          <div className="topic-card-title-info">
            <div className="topic-card-title-row">
              <h3 className="topic-card-name">{topic.name}</h3>
              <div className={`topic-status-pill ${topic.status === 'active' ? 'active' : 'paused'}`}>
                <span className="topic-status-dot">
                  <span className="topic-status-dot-inner" />
                  {topic.status === 'active' && <span className="topic-status-dot-ring" />}
                </span>
                {topic.status === 'active' ? 'Live' : 'Paused'}
              </div>
            </div>
            <p className="topic-card-updated">Updated {timeAgo(topic.last_crawl_at)}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
            onClick={() => onPin(topic.id, !topic.is_pinned)}
            title={topic.is_pinned ? 'Unpin' : 'Pin'}
          >
            <Pin size={13} />
          </button>
          <button className="topic-card-refresh" onClick={() => onRefresh(topic.id)}>
            <RefreshCw size={11} />
            Refresh
          </button>
        </div>
      </div>

      {/* Description */}
      {topic.last_summary ? (
        <p className="topic-card-summary">{topic.last_summary.split(/\n---\n/)[0]}</p>
      ) : (
        <p className="topic-card-empty">Awaiting first analysis cycle...</p>
      )}

      {/* Metrics tiles */}
      {cardMetrics.length > 0 && (
        <div className="topic-metrics-row">
          {cardMetrics.map((m, i) => (
            <div
              key={i}
              className="topic-metric-chip pop"
              style={{ animationDelay: `${340 + d + i * 70}ms` }}
            >
              <span className="topic-metric-label">{m.label}</span>
              <span
                className="topic-metric-value"
                style={m.color ? { color: m.color } : undefined}
              >
                {m.animate && typeof m.value === 'number' ? <AnimatedNum to={m.value} /> : m.value}
              </span>
              {m.sub && (
                <span
                  className="topic-metric-sub"
                  style={{
                    background: m.subBg,
                    border: `1px solid ${m.subColor}18`,
                    color: m.subColor,
                  }}
                >
                  {m.sub === 'bearish' ? '▼' : '▲'} {m.sub}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Alert — show top 1 only */}
      {alerts.length > 0 && (
        <div className={`topic-card-alert ${alerts[0].level}`}>
          {alerts[0].level === 'critical' ? <AlertCircle size={13} /> : alerts[0].level === 'warning' ? <AlertTriangle size={13} /> : <Info size={13} />}
          <span>{alerts[0].message}</span>
          {alerts.length > 1 && <span className="topic-alert-more">+{alerts.length - 1}</span>}
        </div>
      )}

      {/* Footer: sources + tags */}
      <div className="topic-card-footer">
        <div className="topic-card-sources">
          <span className="topic-card-sources-label">Sources</span>
          {topic.platforms.map((p) => (
            <div key={p} className="topic-source-icon" title={p.toUpperCase()}>
              {p === 'x' ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              )}
            </div>
          ))}
        </div>
        <div className="topic-card-tags">
          {topic.keywords.slice(0, 3).map((kw) => (
            <span key={kw} className="topic-tag">#{kw}</span>
          ))}
          {topic.keywords.length > 3 && (
            <span className="topic-tag">+{topic.keywords.length - 3}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Create Topic Modal ───────────────────────────────────────

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
                className={`topic-tag${platforms.includes(p) ? ' platform' : ''}`}
                style={{ padding: '6px 14px', cursor: 'pointer' }}
                onClick={() => togglePlatform(p)}
              >{p.toUpperCase()}</button>
            ))}
          </div>
        </div>
        <Input label="Keywords (comma-separated)" placeholder="e.g. Elon Musk, SpaceX, Tesla" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <Input label="Refresh Interval (hours)" type="number" min={1} value={interval} onChange={(e) => setInterval(e.target.value)} />
        <button className="btn btn-primary" style={{ width: '100%', marginTop: 8 }} disabled={!name.trim() || platforms.length === 0 || isLoading} onClick={handleSubmit}>
          <Plus size={16} />
          {isLoading ? 'Creating...' : 'Create Topic'}
        </button>
      </div>
    </Modal>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────

export function DashboardPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState<'All' | 'Active' | 'Paused'>('All')

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

  const allTopics = topics ?? []
  const filtered = filter === 'All' ? allTopics : filter === 'Active' ? allTopics.filter((t) => t.status === 'active') : allTopics.filter((t) => t.status === 'paused')
  const totalPosts = allTopics.reduce((s, t) => s + t.total_contents, 0)

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header rise">
        <div>
          <h1>Dashboard</h1>
          <p className="dashboard-subtitle">
            Tracking {allTopics.length} topics · {totalPosts} posts collected
          </p>
        </div>
        <button className="btn-accent" onClick={() => setShowCreate(true)}>
          <Plus size={15} />
          New Topic
        </button>
      </div>

      {/* Stats */}
      <div className="dashboard-stats rise" style={{ animationDelay: '80ms' }}>
        {[
          { label: 'Topics', value: allTopics.length, emoji: '📋' },
          { label: 'Active', value: allTopics.filter((t) => t.status === 'active').length, emoji: '🟢' },
        ].map((s, i) => (
          <div key={i} className="dash-stat pop" style={{ animationDelay: `${130 + i * 70}ms` }}>
            <span className="dash-stat-emoji">{s.emoji}</span>
            <div className="dash-stat-content">
              <span className="dash-stat-label">{s.label}</span>
              <span className="dash-stat-value">
                {typeof s.value === 'number' ? <AnimatedNum to={s.value} /> : s.value}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div className="dashboard-filter-bar rise" style={{ animationDelay: '180ms' }}>
        <span className="dashboard-topics-label">Topics</span>
        <div className="filter-pills">
          {(['All', 'Active', 'Paused'] as const).map((f) => (
            <button
              key={f}
              className={`filter-pill${filter === f ? ' filter-pill-active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Topic cards */}
      {topicsLoading ? (
        <div className="topic-grid">
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
        </div>
      ) : filtered.length > 0 ? (
        <DragDropProvider onDragEnd={handleDragEnd}>
          <div className="topic-grid">
            {filtered.map((topic, index) => (
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
        <div className="topic-empty-state pop">
          <span style={{ fontSize: '2.5rem' }}>📊</span>
          <h3>No {filter.toLowerCase()} topics found</h3>
          <p>Create your first monitoring topic to get started</p>
          <button className="btn-accent" onClick={() => setShowCreate(true)}>
            <Plus size={15} />
            Create Topic
          </button>
        </div>
      )}

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
