import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Clock, AlertCircle, AlertTriangle, Info, Search, Trash2, Pause, Play } from 'lucide-react'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import {
  useGetTopicQuery,
  useRefreshTopicMutation,
  useReanalyzeTopicMutation,
  useUpdateTopicMutation,
  useDeleteTopicMutation,
} from '@/store/api'
import type { TopicAlert } from '@/types/models'
import { useTimezone } from '@/hooks/useTimezone'

function normalizeAlert(alert: TopicAlert): { level: string; message: string } {
  if (typeof alert === 'string') return { level: 'info', message: alert }
  return alert
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
      .map(([k, val]) => `${k}: ${typeof val === 'number' ? fmtMetricValue(val) : val}`)
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
  const [reanalyzeTopic, { isLoading: isReanalyzing }] = useReanalyzeTopicMutation()
  const [updateTopic] = useUpdateTopicMutation()
  const [deleteTopic] = useDeleteTopicMutation()
  const { fmt } = useTimezone()

  if (isLoading) {
    return (
      <div className="stack rise">
        <div style={{ height: 32 }}><Skeleton className="w-48 h-full" /></div>
        <div style={{ height: 256 }}><Skeleton className="w-full h-full" /></div>
      </div>
    )
  }

  if (isError || !topic || ('error' in topic)) {
    return (
      <div className="stack rise">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} /> Back
        </Button>
        <p style={{ color: 'var(--negative)' }}>Topic not found</p>
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
    <div className="topic-detail rise">
      {/* Header */}
      <div className="topic-detail-header">
        <div className="topic-detail-title">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft size={16} />
          </Button>
          <div className="topic-card-icon-box" style={{ width: 40, height: 40, borderRadius: 12, fontSize: 18 }}>
            {topic.icon}
          </div>
          <h1>{topic.name}</h1>
          <div className={`topic-status-pill ${topic.status === 'active' ? 'active' : 'paused'}`}>
            <span className="topic-status-dot">
              <span className="topic-status-dot-inner" />
              {topic.status === 'active' && <span className="topic-status-dot-ring" />}
            </span>
            {topic.status === 'active' ? 'Live' : 'Paused'}
          </div>
        </div>
        <div className="topic-detail-actions">
          <button className="topic-card-refresh" onClick={() => refreshTopic(topic.id)} disabled={isRefreshing || topic.status !== 'active'}>
            <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <button className="topic-card-refresh" onClick={() => reanalyzeTopic(topic.id)} disabled={isReanalyzing}>
            <RefreshCw size={13} className={isReanalyzing ? 'animate-spin' : ''} />
            {isReanalyzing ? 'Analyzing...' : 'Reanalyze'}
          </button>
          <Button size="sm" variant="ghost" onClick={handleTogglePause}>
            {topic.status === 'active' ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDelete} style={{ color: 'var(--negative)' }}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Info strip */}
      <div className="topic-detail-info pop" style={{ animationDelay: '80ms' }}>
        <div className="topic-detail-info-item">
          <span className="label">Created</span>
          <span>{fmt(topic.created_at)}</span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Last Crawl</span>
          <span>{fmt(topic.last_crawl_at)}</span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Contents</span>
          <span style={{ fontWeight: 800, fontSize: '1.125rem' }}>{topic.total_contents}</span>
        </div>
        <div className="topic-detail-info-item">
          <span className="label">Platforms</span>
          <span style={{ display: 'flex', gap: 4 }}>
            {(topic.platforms ?? []).map((p) => (
              <span key={p} className="topic-tag platform">{(p ?? '').toUpperCase()}</span>
            ))}
          </span>
        </div>
      </div>

      {/* Keywords */}
      {(topic.keywords ?? []).length > 0 && (
        <div className="topic-card-tags" style={{ padding: 0 }}>
          {(topic.keywords ?? []).map((kw) => <span key={kw} className="topic-tag">#{kw}</span>)}
        </div>
      )}

      {/* Summary */}
      {topic.last_summary && (() => {
        const parts = topic.last_summary.split(/\n---\n/)
        const zhPart = parts[0]?.trim()
        const enPart = parts[1]?.trim()
        return (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Summary</CardDescription>
            </CardHeader>
            <div style={{ fontFamily: "'Outfit', system-ui, sans-serif", fontSize: '0.875rem', lineHeight: 1.8, color: 'var(--ink)', whiteSpace: 'pre-wrap' }}>
              {zhPart}
            </div>
            {enPart && (
              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--glass-border)', fontFamily: "'Outfit', system-ui, sans-serif", fontSize: '0.8125rem', lineHeight: 1.8, color: 'var(--ink-2)', whiteSpace: 'pre-wrap' }}>
                {enPart}
              </div>
            )}
            {topic.summary_data?.cycle_id && (
              <div style={{ marginTop: 12, fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', color: 'var(--ink-3)' }}>
                <Clock size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                Cycle: {topic.summary_data.cycle_id}
              </div>
            )}
          </CardContent>
        </Card>
        )
      })()}

      {/* Metrics */}
      {metricEntries.length > 0 && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Metrics</CardDescription>
            </CardHeader>
            <div className="topic-detail-metrics-grid">
              {metricEntries.map(([key, value]) => (
                <div key={key} className="topic-detail-metric-item pop" style={{ animationDelay: '100ms' }}>
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
                  <Search size={13} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
                  <span className="topic-tag platform">{(rec.platform ?? '').toUpperCase()}</span>
                  <span style={{ flex: 1, fontSize: '0.8125rem' }}>{rec.query ?? ''}</span>
                  <Badge variant={rec.priority === 'high' ? 'error' : rec.priority === 'medium' ? 'warning' : 'muted'}>
                    {rec.priority ?? 'low'}
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
          <summary style={{ fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', cursor: 'pointer', color: 'var(--ink-3)', padding: '8px 0' }}>
            Raw summary data
          </summary>
          <pre style={{
            fontFamily: "'Space Mono', monospace",
            fontSize: '0.6875rem',
            overflow: 'auto',
            padding: 16,
            marginTop: 8,
            background: 'var(--glass)',
            backdropFilter: 'blur(12px)',
            borderRadius: 14,
            maxHeight: 400,
            border: '1px solid var(--glass-border)',
            color: 'var(--ink-2)',
          }}>
            {JSON.stringify(topic.summary_data, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
