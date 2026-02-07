import { Bot, Layers } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListAgentsQuery, useListQueuesQuery, useListTasksQuery } from '@/store/api'
import { AgentCard } from './AgentCard'

export function AgentsPage() {
  const { data: agents, isLoading: agentsLoading } = useListAgentsQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: queues, isLoading: queuesLoading } = useListQueuesQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: tasksData, isLoading: tasksLoading } = useListTasksQuery({ limit: 20 }, {
    pollingInterval: 5000,
  })

  const recentTasks = tasksData?.tasks ?? []

  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <Bot size={20} />
        <h1 className="text-xl font-semibold">Agents</h1>
      </div>

      {/* Task Queues */}
      <Card>
        <CardContent>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers size={18} />
              Task Queues
            </CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {queuesLoading ? (
              <Skeleton className="w-full h-10" />
            ) : queues && queues.length > 0 ? (
              queues.map((q) => (
                <div key={q.label} className="flex items-center justify-between py-2">
                  <Badge variant="muted">{q.label}</Badge>
                  <span className="font-medium">{q.pending} pending</span>
                </div>
              ))
            ) : (
              <p style={{ color: 'var(--foreground-subtle)' }}>No queues active</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Agent Cards */}
      {agentsLoading ? (
        <div className="stats-grid">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="w-full h-48" />
          ))}
        </div>
      ) : agents && agents.length > 0 ? (
        <div className="stats-grid">
          {agents.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      ) : (
        <p style={{ color: 'var(--foreground-subtle)' }}>No agents connected</p>
      )}

      {/* Recent Completed Tasks */}
      <Card>
        <CardContent>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {tasksLoading ? (
              <Skeleton className="w-full h-10" />
            ) : recentTasks.length > 0 ? (
              recentTasks.map((task) => (
                <div key={task.id} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-3">
                    <Badge variant="muted">{task.label}</Badge>
                    <span className="text-sm font-mono" style={{ color: 'var(--foreground-muted)' }}>
                      {task.id.slice(0, 8)}
                    </span>
                    {task.assigned_to && (
                      <span className="text-sm" style={{ color: 'var(--foreground-subtle)' }}>
                        → {task.assigned_to}
                      </span>
                    )}
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
              <p style={{ color: 'var(--foreground-subtle)' }}>No recent activity</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
