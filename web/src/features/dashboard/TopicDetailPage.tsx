import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Clock, AlertCircle, AlertTriangle, Info, Search, Trash2, Pause, Play } from 'lucide-react'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import {
  useGetTopicQuery,
  useRefreshTopicMutation,
  useUpdateTopicMutation,
  useDeleteTopicMutation,
} from '@/store/api'
import type { TopicAlert } from '@/types/models'

function normalizeAlert(alert: TopicAlert): { level: string; message: string } {
  if (typeof alert === 'string') return { level: 'info', message: alert }
  return alert
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

function fmtMetricValue(v: unknown): string {
  if (v == null) return '-'
  if (typeof v === 'number') {
    if (v >= 100_000) return `${(v / 1000).toFixed(0)}k`
    if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
    return String(v)
  }
  if (typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${typeof val === 'number' ? `${Math.round(val * 100)}%` : val}`)
      .join(', ')
  }
  return String(v)
}

function metricLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function TopicDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: topic, isLoading, isError } = useGetTopicQuery(id ?? '', { skip: !id, pollingInterval: 10000 })
  const [refreshTopic, { isLoading: isRefreshing }] = useRefreshTopicMutation()
  const [updateTopic] = useUpdateTopicMutation()
  const [deleteTopic] = useDeleteTopicMutation()

  if (isLoading) {
    return (
      <div className="stack">
        <Skeleton className="w-48 h-8" />
        <Skeleton className="w-full h-64" />
      </div>
    )
  }

  if (isError || !topic || ('error' in topic)) {
    return (
      <div className="stack">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <p style={{ color: 'var(--error)' }}>Topic not found</p>
      </div>
    )
  }

  const alerts = (topic.summary_data?.alerts ?? []).map(normalizeAlert)
  const metrics = topic.summary_data?.metrics ?? {}
  const metricEntries = Object.entries(metrics)
  const recommendations = topic.summary_data?.recommended_next_queries ?? []

  const handleTogglePause = async () => {
    await updateTopic({ id: topic.id, status: topic.status === 'active' ? 'paused' : 'active' })
  }

  const handleDelete = async () => {
    await deleteTopic(topic.id)
    navigate('/')
  }

  return (
    <div className="topic-detail">
      {/* Header */}
      <div className="topic-detail-header">
        <div className="topic-detail-title">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft size={16} />
          </Button>
          <span className="topic-detail-icon">{topic.icon}</span>
          <h1>{topic.name}</h1>
          <Badge variant={topic.status === 'active' ? 'success' : topic.status === 'paused' ? 'warning' : 'error'}>
            {topic.status}
          </Badge>
        </div>
        <div className="topic-detail-actions">
          <Button size="sm" variant="ghost" onClick={() => refreshTopic(topic.id)} disabled={isRefreshing || topic.status !== 'active'}>
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleTogglePause}>
            {topic.status === 'active' ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDelete} style={{ color: 'var(--error)' }}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Info strip */}
      <div className="topic-detail-info">
        <div className="topic-detail-info-item">
          <span className="label">Created</span>
          <span>{formatDate(topic.created_at)}</span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Last Crawl</span>
          <span>{formatDate(topic.last_crawl_at)}</span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Contents</span>
          <span><strong>{topic.total_contents}</strong></span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Platforms</span>
          <span>{topic.platforms.map((p) => <Badge key={p} variant="muted" style={{ marginRight: 4 }}>{p.toUpperCase()}</Badge>)}</span>
        </div>
      </div>

      {/* Keywords */}
      {topic.keywords.length > 0 && (
        <div className="topic-card-tags" style={{ padding: 0 }}>
          {topic.keywords.map((kw) => <span key={kw} className="topic-tag">{kw}</span>)}
        </div>
      )}

      {/* Summary */}
      {topic.last_summary && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Summary</CardDescription>
            </CardHeader>
            <div style={{ fontSize: '0.875rem', lineHeight: 1.8, color: 'var(--foreground)', whiteSpace: 'pre-wrap' }}>
              {topic.last_summary}
            </div>
            {topic.summary_data?.cycle_id && (
              <div style={{ marginTop: 12, fontSize: '0.75rem', color: 'var(--foreground-subtle)' }}>
                <Clock size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                Cycle: {topic.summary_data.cycle_id}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Metrics — render all dynamically */}
      {metricEntries.length > 0 && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Metrics</CardDescription>
            </CardHeader>
            <div className="topic-detail-metrics-grid">
              {metricEntries.map(([key, value]) => (
                <div key={key} className="topic-detail-metric-item">
                  <span className="topic-detail-metric-value">{fmtMetricValue(value)}</span>
                  <span className="topic-detail-metric-label">{metricLabel(key)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Alerts */}
      {alerts.length > 0 && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Alerts ({alerts.length})</CardDescription>
            </CardHeader>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {alerts.map((alert, i) => (
                <div key={i} className={`topic-card-alert ${alert.level}`} style={{ margin: 0 }}>
                  {alert.level === 'critical' ? <AlertCircle size={14} /> : alert.level === 'warning' ? <AlertTriangle size={14} /> : <Info size={14} />}
                  <span>{alert.message}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recommended Next Queries */}
      {recommendations.length > 0 && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Recommended Queries</CardDescription>
            </CardHeader>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {recommendations.map((rec, i) => (
                <div key={i} className="topic-detail-query-row">
                  <Search size={13} style={{ color: 'var(--foreground-subtle)', flexShrink: 0 }} />
                  <Badge variant="muted">{rec.platform.toUpperCase()}</Badge>
                  <span style={{ flex: 1, fontSize: '0.8125rem' }}>{rec.query}</span>
                  <Badge variant={rec.priority === 'high' ? 'error' : rec.priority === 'medium' ? 'warning' : 'muted'}>
                    {rec.priority}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Raw data */}
      {topic.summary_data && (
        <details style={{ marginTop: 8 }}>
          <summary className="text-xs cursor-pointer" style={{ color: 'var(--foreground-subtle)', padding: '8px 0' }}>Raw summary data</summary>
          <pre className="text-xs overflow-auto p-3 mt-2" style={{ background: 'rgba(100,116,139,0.04)', borderRadius: 8, maxHeight: 400, border: '1px solid rgba(100,116,139,0.1)' }}>
            {JSON.stringify(topic.summary_data, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
