import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { StatusDot } from '@/components/ui/StatusDot'
import type { AgentHeartbeat } from '@/types/models'

interface AgentCardProps {
  agent: AgentHeartbeat
}

export function AgentCard({ agent }: AgentCardProps) {
  const uptimeStr = formatUptime(agent.started_at)

  return (
    <Card className="agent-page-card">
      <CardContent>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <StatusDot status={agent.status === 'error' ? 'error' : 'running'} />
              {agent.name}
            </CardTitle>
            <Badge
              variant={
                agent.status === 'busy' ? 'warning' :
                agent.status === 'idle' ? 'success' :
                'error'
              }
            >
              {agent.status}
            </Badge>
          </div>
        </CardHeader>

        <div className="stack-sm" style={{ marginTop: '1rem' }}>
          <div className="flex items-center gap-2 flex-wrap">
            {agent.labels.map((label) => (
              <Badge key={label} variant="muted">{label}</Badge>
            ))}
          </div>

          {agent.current_task_label && (
            <div className="flex items-center gap-2 text-sm">
              <span style={{ color: 'var(--foreground-muted)' }}>Working on:</span>
              <Badge variant="warning">{agent.current_task_label}</Badge>
              {agent.current_task_id && (
                <span className="font-mono" style={{ color: 'var(--foreground-muted)' }}>
                  {agent.current_task_id.slice(0, 8)}
                </span>
              )}
            </div>
          )}

          <div className="agent-stats">
            <div className="flex justify-between text-sm">
              <span style={{ color: 'var(--foreground-muted)' }}>Completed</span>
              <span className="font-medium">{agent.tasks_completed}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span style={{ color: 'var(--foreground-muted)' }}>Failed</span>
              <span className="font-medium">{agent.tasks_failed}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span style={{ color: 'var(--foreground-muted)' }}>Uptime</span>
              <span className="font-medium">{uptimeStr}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function formatUptime(startedAt: string): string {
  const seconds = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
}
