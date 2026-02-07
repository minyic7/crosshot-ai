import { Activity, CheckCircle, AlertCircle, Clock, Bot } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { StatusDot } from '@/components/ui/StatusDot'
import { Skeleton } from '@/components/ui/Skeleton'
import { useGetHealthQuery, useGetDashboardStatsQuery, useListAgentsQuery, useListTasksQuery } from '@/store/api'

export function DashboardPage() {
  const { data: health, isLoading: healthLoading } = useGetHealthQuery(undefined, {
    pollingInterval: 10000,
  })
  const { data: stats, isLoading: statsLoading } = useGetDashboardStatsQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: agents, isLoading: agentsLoading } = useListAgentsQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: tasksData, isLoading: tasksLoading } = useListTasksQuery({ limit: 10 }, {
    pollingInterval: 5000,
  })

  const tasks = tasksData?.tasks ?? []

  return (
    <div className="stack">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        {healthLoading ? (
          <Skeleton className="w-20 h-6" />
        ) : (
          <Badge variant={health?.status === 'ok' ? 'success' : 'error'}>
            {health?.status === 'ok' ? 'System Online' : 'System Down'}
          </Badge>
        )}
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Pending</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <Clock size={20} style={{ color: 'var(--warning)' }} />
                    {stats?.total_pending ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Agents Online</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <Activity size={20} style={{ color: 'var(--blue)' }} />
                    {stats?.agents_online ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Completed</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <CheckCircle size={20} style={{ color: 'var(--success)' }} />
                    {stats?.recent_completed ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>

        <Card className="glass-card-static">
          <CardContent>
            <CardHeader>
              <CardDescription>Failed</CardDescription>
              <CardTitle>
                {statsLoading ? <Skeleton className="w-12 h-8" /> : (
                  <span className="text-2xl flex items-center gap-2">
                    <AlertCircle size={20} style={{ color: 'var(--error)' }} />
                    {stats?.recent_failed ?? 0}
                  </span>
                )}
              </CardTitle>
            </CardHeader>
          </CardContent>
        </Card>
      </div>

      {/* Agents Overview */}
      <Card>
        <CardContent>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot size={18} />
              Agents
            </CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {agentsLoading ? (
              <>
                <Skeleton className="w-full h-10" />
                <Skeleton className="w-full h-10" />
              </>
            ) : agents && agents.length > 0 ? (
              agents.map((agent) => (
                <div key={agent.name} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-3">
                    <StatusDot status={agent.status === 'busy' ? 'running' : agent.status === 'idle' ? 'running' : 'error'} />
                    <span className="font-medium">{agent.name}</span>
                    {agent.current_task_label && (
                      <Badge variant="warning">{agent.current_task_label}</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {agent.labels.map((label) => (
                      <Badge key={label} variant="muted">{label}</Badge>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <p style={{ color: 'var(--foreground-subtle)' }}>No agents connected</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Recent Tasks */}
      <Card>
        <CardContent>
          <CardHeader>
            <CardTitle>Recent Tasks</CardTitle>
          </CardHeader>
          <div className="stack-sm" style={{ marginTop: '1rem' }}>
            {tasksLoading ? (
              <>
                <Skeleton className="w-full h-10" />
                <Skeleton className="w-full h-10" />
                <Skeleton className="w-full h-10" />
              </>
            ) : tasks.length > 0 ? (
              tasks.slice(0, 10).map((task) => (
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
              <p style={{ color: 'var(--foreground-subtle)' }}>No tasks yet</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
