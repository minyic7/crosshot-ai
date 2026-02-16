import { useState } from 'react'
import { Clock, Loader2, CheckCircle2, XCircle, ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { useTimezone } from '@/hooks/useTimezone'
import type { Task, TaskStatus } from '@/types/models'

const STATUS_ICON: Record<TaskStatus, React.ReactNode> = {
  pending: <Clock size={14} style={{ color: 'var(--ink-3)' }} />,
  running: <Loader2 size={14} className="animate-spin" style={{ color: 'var(--warning)' }} />,
  completed: <CheckCircle2 size={14} style={{ color: 'var(--positive)' }} />,
  failed: <XCircle size={14} style={{ color: 'var(--negative)' }} />,
}

function actionSummary(payload: Record<string, unknown>): string {
  const action = payload.action as string
  if (action === 'search') {
    const q = (payload.query as string) ?? ''
    return `Search: ${q.slice(0, 40)}${q.length > 40 ? '...' : ''}`
  }
  if (action === 'tweet') return `Tweet: ${(payload.url as string)?.slice(0, 36) ?? (payload.tweet_id as string) ?? ''}`
  if (action === 'timeline') return `Timeline: @${payload.username as string}`
  return action ?? ''
}

function payloadSummary(payload: Record<string, unknown>): { label: string; value: string }[] {
  const items: { label: string; value: string }[] = []
  if (payload.action) items.push({ label: 'Action', value: String(payload.action) })
  if (payload.query) items.push({ label: 'Query', value: String(payload.query) })
  if (payload.username) items.push({ label: 'User', value: `@${payload.username}` })
  if (payload.tweet_id) items.push({ label: 'Tweet', value: String(payload.tweet_id) })
  if (payload.url) items.push({ label: 'URL', value: String(payload.url) })
  if (payload.max_tweets) items.push({ label: 'Max', value: String(payload.max_tweets) })
  if (payload.search_tab) items.push({ label: 'Tab', value: String(payload.search_tab) })
  if (payload.topic_id) items.push({ label: 'Topic', value: String(payload.topic_id).slice(0, 8) + '...' })
  return items
}

interface TaskLineProps {
  task: Task
}

export function TaskLine({ task }: TaskLineProps) {
  const [expanded, setExpanded] = useState(false)
  const { fmt, fmtRelative } = useTimezone()
  const result = task.result as Record<string, unknown> | null

  return (
    <div className={`task-line${expanded ? ' task-line-open' : ''}`}>
      {/* Collapsed row */}
      <div className="task-line-row" onClick={() => setExpanded(!expanded)}>
        <span className="task-line-icon">
          {STATUS_ICON[task.status] ?? STATUS_ICON.pending}
        </span>
        <Badge variant="muted" style={{ fontSize: '0.6875rem', padding: '1px 8px' }}>
          {task.label}
        </Badge>
        <span className="task-line-id">{task.id.slice(0, 8)}</span>
        <span className="task-line-summary">{actionSummary(task.payload)}</span>
        {task.assigned_to && (
          <span className="task-line-agent">{task.assigned_to}</span>
        )}
        {result && (result.tweets_found !== undefined) && (
          <Badge variant="muted" style={{ fontSize: '0.625rem', padding: '1px 6px' }}>
            {result.tweets_found as number} found
          </Badge>
        )}
        <span className="task-line-time">{fmtRelative(task.created_at)}</span>
        <ChevronDown
          size={14}
          style={{
            color: 'var(--ink-3)',
            transition: 'transform 0.2s ease',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0)',
            flexShrink: 0,
          }}
        />
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="task-line-detail">
          {/* Progress row */}
          <div className="task-line-detail-grid">
            <div>
              <span className="task-line-detail-label">Status</span>
              <Badge
                variant={
                  task.status === 'completed' ? 'success' :
                  task.status === 'failed' ? 'error' :
                  task.status === 'running' ? 'warning' : 'muted'
                }
              >
                {task.status}
              </Badge>
            </div>
            <div>
              <span className="task-line-detail-label">Agent</span>
              <span className="task-line-detail-value">{task.assigned_to ?? '-'}</span>
            </div>
            <div>
              <span className="task-line-detail-label">Retries</span>
              <span className="task-line-detail-value">{task.retry_count}/{task.max_retries}</span>
            </div>
            <div>
              <span className="task-line-detail-label">Priority</span>
              <span className="task-line-detail-value">
                {task.priority === 2 ? 'High' : task.priority === 1 ? 'Medium' : 'Low'}
              </span>
            </div>
          </div>

          {/* Timestamps */}
          <div className="task-line-detail-grid" style={{ marginTop: 8 }}>
            <div>
              <span className="task-line-detail-label">Created</span>
              <span className="task-line-detail-value">{fmt(task.created_at)}</span>
            </div>
            <div>
              <span className="task-line-detail-label">Started</span>
              <span className="task-line-detail-value">{fmt(task.started_at)}</span>
            </div>
            <div>
              <span className="task-line-detail-label">Completed</span>
              <span className="task-line-detail-value">{fmt(task.completed_at)}</span>
            </div>
          </div>

          {/* Payload */}
          <div style={{ marginTop: 10 }}>
            <span className="task-line-detail-label">Payload</span>
            <div className="task-line-payload">
              {payloadSummary(task.payload).map(({ label, value }) => (
                <div key={label} className="task-line-payload-item">
                  <span className="task-line-payload-key">{label}</span>
                  <span className="task-line-payload-val">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Error */}
          {task.error && (
            <div style={{ marginTop: 8 }}>
              <span className="task-line-detail-label">Error</span>
              <pre className="task-line-error">{task.error}</pre>
            </div>
          )}

          {/* Result summary */}
          {result && (
            <div style={{ marginTop: 8 }}>
              <details>
                <summary className="task-line-detail-label" style={{ cursor: 'pointer' }}>
                  Result JSON
                </summary>
                <pre className="task-line-json">{JSON.stringify(result, null, 2)}</pre>
              </details>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
