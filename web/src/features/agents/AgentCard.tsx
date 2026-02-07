import { Terminal } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { StatusDot } from '@/components/ui/StatusDot'
import { Button } from '@/components/ui/Button'
import type { Agent } from '@/types/models'

interface AgentCardProps {
  agent: Agent
  onViewLogs: () => void
}

export function AgentCard({ agent, onViewLogs }: AgentCardProps) {
  const uptimeStr = formatUptime(agent.uptime_seconds)

  return (
    <Card className="agent-page-card">
      <CardContent>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <StatusDot status={agent.status} />
              {agent.name}
            </CardTitle>
            <Badge
              variant={
                agent.status === 'running' ? 'success' :
                agent.status === 'error' ? 'error' :
                'muted'
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

          <Button variant="ghost" size="sm" onClick={onViewLogs}>
            <Terminal size={14} />
            View Logs
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
}
