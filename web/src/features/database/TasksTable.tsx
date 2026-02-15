import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListTasksQuery } from '@/store/api'
import { useTimezone } from '@/hooks/useTimezone'
import type { TaskStatus } from '@/types/models'

export function TasksTable() {
  const [statusFilter, setStatusFilter] = useState<TaskStatus | ''>('')
  const navigate = useNavigate()
  const { fmt } = useTimezone()
  const { data, isLoading } = useListTasksQuery(
    statusFilter ? { status: statusFilter } : undefined,
    { pollingInterval: 5000 },
  )

  const tasks = data?.tasks ?? []

  return (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm font-medium" style={{ color: 'var(--foreground-muted)' }}>Filter:</span>
          {(['', 'pending', 'running', 'completed', 'failed'] as const).map((s) => (
            <button
              key={s}
              className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setStatusFilter(s as TaskStatus | '')}
            >
              {s || 'All'}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="stack-sm">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="w-full h-12" />
            ))}
          </div>
        ) : (
          <div className="table-compact">
            <div className="table-compact-row" style={{ fontWeight: 600, borderBottom: '2px solid var(--border-default)' }}>
              <span style={{ flex: 1 }}>ID</span>
              <span style={{ flex: 1 }}>Label</span>
              <span style={{ flex: 0.7 }}>Agent</span>
              <span style={{ flex: 0.5 }}>Status</span>
              <span style={{ flex: 1 }}>Created</span>
            </div>
            {tasks.length > 0 ? (
              tasks.map((task) => (
                <div
                  key={task.id}
                  className="table-compact-row"
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/task/${task.id}`)}
                >
                  <span style={{ flex: 1 }} className="font-mono text-sm">
                    {task.id.slice(0, 8)}...
                  </span>
                  <span style={{ flex: 1 }}>
                    <Badge variant="muted">{task.label}</Badge>
                  </span>
                  <span style={{ flex: 0.7 }} className="text-sm">
                    {task.assigned_to || '-'}
                  </span>
                  <span style={{ flex: 0.5 }}>
                    <Badge
                      variant={
                        task.status === 'completed' ? 'success' :
                        task.status === 'failed' ? 'error' :
                        task.status === 'running' ? 'warning' :
                        'muted'
                      }
                    >
                      {task.status}
                    </Badge>
                  </span>
                  <span style={{ flex: 1 }} className="text-sm">
                    {fmt(task.created_at)}
                  </span>
                </div>
              ))
            ) : (
              <p className="py-4 text-center" style={{ color: 'var(--foreground-subtle)' }}>No tasks found</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
