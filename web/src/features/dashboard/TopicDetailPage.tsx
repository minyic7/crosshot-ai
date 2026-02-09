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
  const metrics = topic.summary_data?.metrics
  const recommendations = topic.summary_data?.recommended_next_queries ?? []
  const platformsCoverage = metrics?.platforms_coverage ?? {}

  const handleTogglePause = async () => {
    await updateTopic({
      id: topic.id,
      status: topic.status === 'active' ? 'paused' : 'active',
    })
  }

  const handleDelete = async () => {
    await deleteTopic(topic.id)
    navigate('/')
  }

  return (
    <div className="stack">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft size={16} className="mr-1" /> Back
          </Button>
          <span style={{ fontSize: '1.5rem' }}>{topic.icon}</span>
          <h1 className="text-xl font-semibold">{topic.name}</h1>
          <Badge variant={topic.status === 'active' ? 'success' : topic.status === 'paused' ? 'warning' : 'error'}>
            {topic.status}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => refreshTopic(topic.id)}
            disabled={isRefreshing || topic.status !== 'active'}
          >
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleTogglePause}>
            {topic.status === 'active' ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDelete} style={{ color: 'var(--error)' }}>
            <Trash2 size={14} /> Delete
          </Button>
        </div>
      </div>

      {/* Info Card */}
      <Card>
        <CardContent>
          <CardHeader className="mb-3">
            <CardDescription>Info</CardDescription>
          </CardHeader>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span style={{ color: 'var(--foreground-muted)' }}>ID:</span> <code className="text-xs">{topic.id}</code></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Status:</span> <Badge variant={topic.status === 'active' ? 'success' : topic.status === 'paused' ? 'warning' : 'muted'}>{topic.status}</Badge></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Created:</span> {formatDate(topic.created_at)}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Updated:</span> {formatDate(topic.updated_at)}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Last Crawl:</span> {formatDate(topic.last_crawl_at)}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Total Contents:</span> <strong>{topic.total_contents}</strong></div>
            {topic.description && (
              <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--foreground-muted)' }}>Description:</span> {topic.description}</div>
            )}
          </div>

          {/* Platforms & Keywords */}
          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div>
              <span className="text-sm" style={{ color: 'var(--foreground-muted)', marginRight: 8 }}>Platforms:</span>
              {topic.platforms.map((p) => (
                <Badge key={p} variant="muted" style={{ marginRight: 4 }}>{p.toUpperCase()}</Badge>
              ))}
            </div>
            <div>
              <span className="text-sm" style={{ color: 'var(--foreground-muted)', marginRight: 8 }}>Keywords:</span>
              <div className="insight-keyword-pills" style={{ display: 'inline-flex' }}>
                {topic.keywords.map((kw) => (
                  <span key={kw} className="insight-pill">{kw}</span>
                ))}
              </div>
            </div>
            {topic.config && Object.keys(topic.config).length > 0 && (
              <div>
                <span className="text-sm" style={{ color: 'var(--foreground-muted)', marginRight: 8 }}>Config:</span>
                {Object.entries(topic.config).map(([k, v]) => (
                  <Badge key={k} variant="muted" style={{ marginRight: 4 }}>{k}: {String(v)}</Badge>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Summary */}
      {topic.last_summary && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Summary</CardDescription>
            </CardHeader>
            <div style={{ fontSize: '0.875rem', lineHeight: 1.7, color: 'var(--foreground)', whiteSpace: 'pre-wrap' }}>
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

      {/* Metrics */}
      {metrics && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Metrics</CardDescription>
            </CardHeader>
            <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
              <div className="insight-metric">
                <span className="insight-metric-label">Total Contents</span>
                <span className="insight-metric-value">{metrics.total_contents}</span>
              </div>
              {metrics.engagement_score != null && (
                <div className="insight-metric">
                  <span className="insight-metric-label">Engagement Score</span>
                  <span className="insight-metric-value">{metrics.engagement_score}</span>
                </div>
              )}
              {metrics.trend_velocity && (
                <div className="insight-metric">
                  <span className="insight-metric-label">Trend Velocity</span>
                  <span className={`insight-metric-change ${metrics.trend_velocity === 'rising' ? 'up' : metrics.trend_velocity === 'falling' ? 'down' : ''}`}>
                    {metrics.trend_velocity}
                  </span>
                </div>
              )}
            </div>

            {/* Platform Coverage */}
            {Object.keys(platformsCoverage).length > 0 && (
              <div>
                <span className="text-sm" style={{ color: 'var(--foreground-muted)', fontWeight: 600 }}>Platform Coverage</span>
                <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                  {Object.entries(platformsCoverage).map(([platform, count]) => (
                    <div key={platform} style={{
                      padding: '8px 16px',
                      borderRadius: 8,
                      background: 'rgba(100,116,139,0.06)',
                      textAlign: 'center',
                    }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--foreground-muted)', marginBottom: 4 }}>{platform.toUpperCase()}</div>
                      <div className="insight-metric-value">{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
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
            <div className="insight-detail-entries">
              {alerts.map((alert, i) => (
                <div key={i} className={`insight-alert insight-alert-${alert.level === 'critical' ? 'critical' : alert.level === 'warning' ? 'warning' : 'info'}`}>
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
              <CardDescription>Recommended Next Queries</CardDescription>
            </CardHeader>
            <div className="stack-sm">
              {recommendations.map((rec, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: 'rgba(100,116,139,0.04)',
                }}>
                  <Search size={14} style={{ color: 'var(--foreground-subtle)', flexShrink: 0 }} />
                  <Badge variant="muted" style={{ flexShrink: 0 }}>{rec.platform.toUpperCase()}</Badge>
                  <span className="text-sm" style={{ flex: 1 }}>{rec.query}</span>
                  <Badge variant={rec.priority === 'high' ? 'error' : rec.priority === 'medium' ? 'warning' : 'muted'}>
                    {rec.priority}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Raw summary_data */}
      {topic.summary_data && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Raw Data</CardDescription>
            </CardHeader>
            <details>
              <summary className="text-xs cursor-pointer" style={{ color: 'var(--foreground-muted)' }}>Show raw JSON</summary>
              <pre className="text-xs overflow-auto p-3 mt-2" style={{ background: 'var(--background)', borderRadius: 8, maxHeight: 400 }}>
                {JSON.stringify(topic.summary_data, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
