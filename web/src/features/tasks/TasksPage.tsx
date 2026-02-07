import { ListTodo } from 'lucide-react'
import { CreateTaskForm } from './CreateTaskForm'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListTasksQuery } from '@/store/api'

export function TasksPage() {
  const { data, isLoading } = useListTasksQuery(
    { limit: 20 },
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
          <CardHeader>
            <CardTitle>Recent Submissions</CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="w-full h-10" />
              ))
            ) : tasks.length > 0 ? (
              tasks.map((task) => (
                <div key={task.id} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm" style={{ color: 'var(--foreground-muted)' }}>
                      {task.id.slice(0, 8)}
                    </span>
                    <Badge variant="muted">{task.label}</Badge>
                  </div>
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
                </div>
              ))
            ) : (
              <p style={{ color: 'var(--foreground-subtle)' }}>No tasks submitted yet</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
