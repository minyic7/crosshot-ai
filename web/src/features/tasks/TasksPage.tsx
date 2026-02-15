import { useNavigate } from 'react-router-dom'
import { ListTodo, Clock, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { CreateTaskForm } from './CreateTaskForm'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListTasksQuery } from '@/store/api'
import { useTimezone } from '@/hooks/useTimezone'

const STATUS_ICON = {
  pending: <Clock size={14} style={{ color: 'var(--foreground-subtle)' }} />,
  running: <Loader2 size={14} className="animate-spin" style={{ color: 'var(--warning)' }} />,
  completed: <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />,
  failed: <XCircle size={14} style={{ color: 'var(--error)' }} />,
} as const

function actionSummary(payload: Record<string, unknown>): string {
  const action = payload.action as string
  if (action === 'search') return `Search: ${(payload.query as string)?.slice(0, 40) ?? ''}${((payload.query as string)?.length ?? 0) > 40 ? '...' : ''}`
  if (action === 'tweet') return `Tweet: ${(payload.url as string)?.slice(0, 40) ?? (payload.tweet_id as string) ?? ''}`
  if (action === 'timeline') return `Timeline: @${payload.username as string}`
  return action ?? ''
}

export function TasksPage() {
  const navigate = useNavigate()
  const { fmtRelative } = useTimezone()
  const { data, isLoading } = useListTasksQuery(
    { limit: 30 },
    { pollingInterval: 5000 },
  )

  const tasks = data?.tasks ?? []

  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <ListTodo size={20} />
        <h1 className="text-xl font-semibold">Tasks</h1>
      </div>

      <CreateTaskForm />

      <Card>
        <CardContent>
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--foreground-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Recent Tasks
          </h3>
          <div className="stack-sm">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="w-full h-12" />
              ))
            ) : tasks.length > 0 ? (
              tasks.map((task) => (
                <div
                  key={task.id}
                  onClick={() => navigate(`/task/${task.id}`)}
                  className="flex items-center gap-3 py-2.5 px-3 rounded-lg transition-colors duration-150"
                  style={{ cursor: 'pointer', marginLeft: '-0.75rem', marginRight: '-0.75rem' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-muted)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  {STATUS_ICON[task.status as keyof typeof STATUS_ICON] ?? STATUS_ICON.pending}
                  <span className="text-sm font-mono" style={{ color: 'var(--foreground-subtle)', minWidth: 60 }}>
                    {task.id.slice(0, 8)}
                  </span>
                  <span className="text-sm flex-1 truncate" style={{ color: 'var(--foreground)' }}>
                    {actionSummary(task.payload)}
                  </span>
                  {task.result && (task.result as Record<string, unknown>).tweets_found !== undefined && (
                    <Badge variant="muted">
                      {(task.result as Record<string, unknown>).tweets_found as number} found
                    </Badge>
                  )}
                  <span className="text-xs" style={{ color: 'var(--foreground-subtle)', minWidth: 50, textAlign: 'right' }}>
                    {fmtRelative(task.created_at)}
                  </span>
                </div>
              ))
            ) : (
              <p className="py-6 text-center text-sm" style={{ color: 'var(--foreground-subtle)' }}>
                No tasks yet. Submit a crawl task above.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
