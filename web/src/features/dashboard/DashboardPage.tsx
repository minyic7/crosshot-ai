import { useState, useCallback } from 'react'
import { Activity, CheckCircle, AlertCircle, Clock, Bot, Plus, GripVertical, Pin, RefreshCw, AlertTriangle, Info } from 'lucide-react'
import { DragDropProvider } from '@dnd-kit/react'
import { useSortable } from '@dnd-kit/react/sortable'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { StatusDot } from '@/components/ui/StatusDot'
import { Skeleton } from '@/components/ui/Skeleton'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import {
  useGetHealthQuery,
  useGetDashboardStatsQuery,
  useListAgentsQuery,
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useRefreshTopicMutation,
  useReorderTopicsMutation,
} from '@/store/api'
import type { Topic } from '@/types/models'

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

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

// ─── Topic Card (sortable) ────────────────────────────────────────

function TopicCard({
  topic,
  index,
  onPin,
  onRefresh,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
}) {
  const { ref, handleRef, isDragging } = useSortable({ id: topic.id, index })
  const alerts = topic.summary_data?.alerts ?? []
  const metrics = topic.summary_data?.metrics

  return (
    <div
      ref={ref}
      className={`glass-card insight-card${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''}${isDragging ? ' drag-over' : ''}`}
    >
      {/* Header */}
      <div className="insight-card-header">
        <div className="insight-card-title-row">
          <span ref={handleRef} className="insight-drag-handle"><GripVertical size={14} /></span>
          <span className="insight-card-icon">{topic.icon}</span>
          <h3>{topic.name}</h3>
          {topic.is_pinned && <span className="insight-pinned-badge">Pinned</span>}
        </div>
        <button
          className={`insight-pin-btn${topic.is_pinned ? ' active' : ''}`}
          onClick={() => onPin(topic.id, !topic.is_pinned)}
          title={topic.is_pinned ? 'Unpin' : 'Pin'}
        >
          <Pin size={14} />
        </button>
      </div>

      {/* Body */}
      <div className="insight-card-body">
        {/* Summary */}
        {topic.last_summary && (
          <div className="insight-summary">
            <div className="insight-sentiment-dot neutral" />
            <p>{topic.last_summary}</p>
          </div>
        )}

        {/* Alerts */}
        {alerts.slice(0, 2).map((alert, i) => (
          <div key={i} className={`insight-alert insight-alert-${alert.level === 'critical' ? 'critical' : alert.level === 'warning' ? 'warning' : 'info'}`}>
            {alert.level === 'critical' ? <AlertCircle size={14} /> : alert.level === 'warning' ? <AlertTriangle size={14} /> : <Info size={14} />}
            <span>{alert.message}</span>
          </div>
        ))}

        {/* Metrics */}
        {metrics && (
          <>
            <div className="insight-metric">
              <span className="insight-metric-label">Contents</span>
              <span className="insight-metric-value">{metrics.total_contents}</span>
            </div>
            {metrics.trend_velocity && (
              <div className="insight-metric">
                <span className="insight-metric-label">Trend</span>
                <span className={`insight-metric-change ${metrics.trend_velocity === 'rising' ? 'up' : metrics.trend_velocity === 'falling' ? 'down' : ''}`}>
                  {metrics.trend_velocity}
                </span>
              </div>
            )}
          </>
        )}

        {/* Keywords */}
        <div className="insight-keyword-pills">
          {topic.platforms.map((p) => (
            <span key={p} className="insight-pill">{p}</span>
          ))}
          {topic.keywords.slice(0, 4).map((kw) => (
            <span key={kw} className="insight-pill">{kw}</span>
          ))}
        </div>

        {/* Empty state if no summary yet */}
        {!topic.last_summary && !metrics && (
          <p style={{ color: 'var(--foreground-subtle)', fontSize: '0.8125rem', fontStyle: 'italic' }}>
            Awaiting first analysis cycle...
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="insight-card-footer">
        <span className="insight-updated">
          <Clock size={11} />
          {timeAgo(topic.last_crawl_at)}
        </span>
        <button className="insight-view-all" onClick={() => onRefresh(topic.id)}>
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
        {/* Emoji picker */}
        <div className="form-group">
          <label className="form-label">Icon</label>
          <div className="emoji-picker">
            {EMOJI_OPTIONS.map((e) => (
              <button
                key={e}
                className={`emoji-option${e === icon ? ' selected' : ''}`}
                onClick={() => setIcon(e)}
              >
                {e}
              </button>
            ))}
          </div>
        </div>

        <Input
          label="Name"
          placeholder="e.g. 马斯克"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <div className="form-group">
          <label className="form-label">Description</label>
          <textarea
            className="form-input form-textarea"
            placeholder="Optional description..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        {/* Platform toggles */}
        <div className="form-group">
          <label className="form-label">Platforms</label>
          <div className="flex gap-2">
            {PLATFORM_OPTIONS.map((p) => (
              <button
                key={p}
                className={`insight-pill${platforms.includes(p) ? '' : ''}`}
                style={{
                  padding: '6px 14px',
                  cursor: 'pointer',
                  border: platforms.includes(p) ? '1.5px solid var(--teal)' : '1px solid rgba(100,116,139,0.2)',
                  background: platforms.includes(p) ? 'rgba(82,96,119,0.1)' : 'transparent',
                  borderRadius: '6px',
                  fontWeight: 500,
                }}
                onClick={() => togglePlatform(p)}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <Input
          label="Keywords (comma-separated)"
          placeholder="e.g. Elon Musk, SpaceX, Tesla"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />

        <Input
          label="Refresh Interval (hours)"
          type="number"
          min={1}
          value={interval}
          onChange={(e) => setInterval(e.target.value)}
        />

        <Button
          className="btn-primary"
          style={{ width: '100%', marginTop: 8 }}
          disabled={!name.trim() || platforms.length === 0 || isLoading}
          onClick={handleSubmit}
        >
          <Plus size={16} />
          {isLoading ? 'Creating...' : 'Create Topic'}
        </Button>
      </div>
    </Modal>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────────

export function DashboardPage() {
  const [showCreate, setShowCreate] = useState(false)

  const { data: health, isLoading: healthLoading } = useGetHealthQuery(undefined, { pollingInterval: 10000 })
  const { data: stats, isLoading: statsLoading } = useGetDashboardStatsQuery(undefined, { pollingInterval: 5000 })
  const { data: agents, isLoading: agentsLoading } = useListAgentsQuery(undefined, { pollingInterval: 5000 })
  const { data: topics, isLoading: topicsLoading } = useListTopicsQuery(undefined, { pollingInterval: 10000 })

  const [updateTopic] = useUpdateTopicMutation()
  const [refreshTopic] = useRefreshTopicMutation()
  const [reorderTopics] = useReorderTopicsMutation()

  const handlePin = useCallback((id: string, pinned: boolean) => {
    updateTopic({ id, is_pinned: pinned })
  }, [updateTopic])

  const handleRefresh = useCallback((id: string) => {
    refreshTopic(id)
  }, [refreshTopic])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleDragEnd = useCallback((event: any) => {
    if (event.canceled || !topics) return
    const { source, target } = event.operation
    if (!source || !target || source.id === target.id) return

    const ids = topics.map((t) => t.id)
    const oldIndex = ids.indexOf(String(source.id))
    const newIndex = ids.indexOf(String(target.id))
    if (oldIndex === -1 || newIndex === -1) return

    const reordered = [...ids]
    const [moved] = reordered.splice(oldIndex, 1)
    reordered.splice(newIndex, 0, moved)
    reorderTopics({ ids: reordered })
  }, [topics, reorderTopics])

  // Separate pinned vs unpinned for display order
  const sortedTopics = topics ?? []

  return (
    <div className="stack">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-2">
          {healthLoading ? (
            <Skeleton className="w-20 h-6" />
          ) : (
            <Badge variant={health?.status === 'ok' ? 'success' : 'error'}>
              {health?.status === 'ok' ? 'System Online' : 'System Down'}
            </Badge>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Pending</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <Clock size={20} style={{ color: 'var(--warning)' }} />
                    {stats?.total_pending ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Agents Online</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <Activity size={20} style={{ color: 'var(--blue)' }} />
                    {stats?.agents_online ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Completed</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <CheckCircle size={20} style={{ color: 'var(--success)' }} />
                    {stats?.recent_completed ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Failed</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <AlertCircle size={20} style={{ color: 'var(--error)' }} />
                    {stats?.recent_failed ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>
      </div>

      {/* Agents Overview */}
      <Card>
        <CardContent>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot size={18} />
              Agents
            </CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {agentsLoading ? (
              <>
                <Skeleton className="w-full h-10" />
                <Skeleton className="w-full h-10" />
              </>
            ) : agents && agents.length > 0 ? (
              agents.map((agent) => (
                <div key={agent.name} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-3">
                    <StatusDot status={agent.status === 'busy' ? 'running' : agent.status === 'idle' ? 'running' : 'error'} />
                    <span className="font-medium">{agent.name}</span>
                    {agent.current_task_label && (
                      <Badge variant="warning">{agent.current_task_label}</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {agent.labels.map((label) => (
                      <Badge key={label} variant="muted">{label}</Badge>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <p style={{ color: 'var(--foreground-subtle)' }}>No agents connected</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Topics Header */}
      <div className="flex items-center justify-between">
        <h2 className="font-semibold" style={{ fontSize: '1.0625rem' }}>Topics</h2>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus size={15} />
          New Topic
        </Button>
      </div>

      {/* Topics Grid */}
      {topicsLoading ? (
        <div className="insight-grid">
          <div style={{ minHeight: 200 }}><Skeleton className="w-full h-full" /></div>
          <div style={{ minHeight: 200 }}><Skeleton className="w-full h-full" /></div>
        </div>
      ) : sortedTopics.length > 0 ? (
        <DragDropProvider onDragEnd={handleDragEnd}>
          <div className="insight-grid">
            {sortedTopics.map((topic, index) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                index={index}
                onPin={handlePin}
                onRefresh={handleRefresh}
              />
            ))}
          </div>
        </DragDropProvider>
      ) : (
        <div className="insight-grid">
          <div className="insight-empty">
            <span style={{ fontSize: '2rem', marginBottom: 8 }}>📊</span>
            <p className="font-medium" style={{ marginBottom: 4 }}>No topics yet</p>
            <p style={{ color: 'var(--foreground-subtle)', fontSize: '0.8125rem', marginBottom: 16 }}>
              Create your first topic to start monitoring
            </p>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus size={15} />
              Create Topic
            </Button>
          </div>
        </div>
      )}

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
