import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { useGetTaskQuery } from '@/store/api'
import type { TaskStatus } from '@/types/models'

const statusVariant = (s: TaskStatus) =>
  s === 'completed' ? 'success' as const :
  s === 'failed' ? 'error' as const :
  s === 'running' ? 'warning' as const :
  'muted' as const

export function TaskDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: task, isLoading, isError } = useGetTaskQuery(id ?? '', { skip: !id })

  if (isLoading) {
    return (
      <div className="stack">
        <Skeleton className="w-48 h-8" />
        <Skeleton className="w-full h-64" />
      </div>
    )
  }

  if (isError || !task || ('error' in task && !task.status)) {
    return (
      <div className="stack">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <p style={{ color: 'var(--error)' }}>Task not found</p>
      </div>
    )
  }

  const result = task.result as Record<string, unknown> | null
  const contentIds = (result?.content_ids as string[] | undefined) ?? []

  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <h1 className="text-xl font-semibold">Task Detail</h1>
      </div>

      {/* Basic info */}
      <Card>
        <CardContent>
          <CardHeader className="mb-3">
            <CardDescription>Info</CardDescription>
          </CardHeader>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span style={{ color: 'var(--foreground-muted)' }}>ID:</span> <code className="text-xs">{task.id}</code></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Label:</span> <Badge variant="muted">{task.label}</Badge></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Status:</span> <Badge variant={statusVariant(task.status)}>{task.status}</Badge></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Priority:</span> {task.priority === 2 ? 'High' : task.priority === 1 ? 'Medium' : 'Low'}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Agent:</span> {task.assigned_to ?? '-'}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Retries:</span> {task.retry_count}/{task.max_retries}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Created:</span> {new Date(task.created_at).toLocaleString()}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Started:</span> {task.started_at ? new Date(task.started_at).toLocaleString() : '-'}</div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Completed:</span> {task.completed_at ? new Date(task.completed_at).toLocaleString() : '-'}</div>
            {task.parent_job_id && (
              <div><span style={{ color: 'var(--foreground-muted)' }}>Job:</span> <code className="text-xs">{task.parent_job_id}</code></div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Payload */}
      <Card>
        <CardContent>
          <CardHeader className="mb-3">
            <CardDescription>Payload</CardDescription>
          </CardHeader>
          <pre className="text-xs overflow-auto p-3" style={{ background: 'var(--background)', borderRadius: 8, maxHeight: 300 }}>
            {JSON.stringify(task.payload, null, 2)}
          </pre>
        </CardContent>
      </Card>

      {/* Error */}
      {task.error && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Error</CardDescription>
            </CardHeader>
            <pre className="text-xs overflow-auto p-3" style={{ background: 'var(--background)', borderRadius: 8, color: 'var(--error)' }}>
              {task.error}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Result</CardDescription>
            </CardHeader>

            {/* Quick summary for search results */}
            {result.action === 'search' && (
              <div className="flex items-center gap-4 mb-3 text-sm">
                <span>Query: <code className="text-xs">{result.query as string}</code></span>
                <span>Tab: <Badge variant="muted">{result.tab as string}</Badge></span>
                <span>Tweets: <strong>{result.tweets_found as number}</strong></span>
              </div>
            )}

            {/* Content links */}
            {contentIds.length > 0 && (
              <div className="mb-3">
                <p className="text-sm mb-2" style={{ color: 'var(--foreground-muted)' }}>Content items ({contentIds.length}):</p>
                <div className="flex flex-wrap gap-1">
                  {contentIds.map((cid) => (
                    <button
                      key={cid}
                      className="btn btn-sm btn-ghost font-mono text-xs"
                      onClick={() => navigate(`/content/${cid}`)}
                    >
                      <ExternalLink size={12} className="mr-1" />
                      {cid.slice(0, 8)}...
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Raw result */}
            <details>
              <summary className="text-xs cursor-pointer" style={{ color: 'var(--foreground-muted)' }}>Raw JSON</summary>
              <pre className="text-xs overflow-auto p-3 mt-2" style={{ background: 'var(--background)', borderRadius: 8, maxHeight: 400 }}>
                {JSON.stringify(result, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
