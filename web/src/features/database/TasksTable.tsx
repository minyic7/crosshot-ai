import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListTasksQuery } from '@/store/api'
import type { TaskStatus } from '@/types/models'

export function TasksTable() {
  const [statusFilter, setStatusFilter] = useState<TaskStatus | ''>('')
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
            <div className="table-compact-row" style={{ fontWeight: 600, borderBottom: '2px solid #e5e7eb' }}>
              <span style={{ flex: 1 }}>ID</span>
              <span style={{ flex: 1 }}>Label</span>
              <span style={{ flex: 0.5 }}>Priority</span>
              <span style={{ flex: 0.5 }}>Status</span>
              <span style={{ flex: 1 }}>Created</span>
            </div>
            {tasks.length > 0 ? (
              tasks.map((task) => (
                <div key={task.id} className="table-compact-row">
                  <span style={{ flex: 1 }} className="font-mono text-sm">
                    {task.id.slice(0, 8)}...
                  </span>
                  <span style={{ flex: 1 }}>
                    <Badge variant="muted">{task.label}</Badge>
                  </span>
                  <span style={{ flex: 0.5 }}>
                    {task.priority === 2 ? 'High' : task.priority === 1 ? 'Medium' : 'Low'}
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
                  <span style={{ flex: 1 }} className="text-sm" >
                    {new Date(task.created_at).toLocaleString()}
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
