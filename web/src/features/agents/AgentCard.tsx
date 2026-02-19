import { useState, useCallback } from 'react'
import { ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { StatusDot } from '@/components/ui/StatusDot'
import { useTap } from '@/hooks/useTap'
import type { AgentHeartbeat } from '@/types/models'

interface AgentCardProps {
  agent: AgentHeartbeat
}

export function AgentCard({ agent }: AgentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const uptime = formatUptime(agent.started_at)
  const tap = useTap(useCallback(() => setExpanded(e => !e), []))

  return (
    <div
      className={`agent-card-v2${expanded ? ' agent-card-v2-open' : ''}${agent.status === 'busy' ? ' agent-card-v2-busy' : ''}`}
      {...tap}
    >
      {/* Shimmer overlay */}
      <div className="agent-card-v2-shimmer" />

      {/* Row 1: Name + Status */}
      <div className="agent-card-v2-header">
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <StatusDot status={agent.status === 'error' ? 'error' : 'running'} />
          <span className="agent-card-v2-name">{agent.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={
              agent.status === 'busy' ? 'warning' :
              agent.status === 'idle' ? 'success' : 'error'
            }
            style={{ fontSize: '0.625rem', padding: '1px 8px' }}
          >
            {agent.status}
          </Badge>
          <ChevronDown
            size={14}
            style={{
              color: 'var(--ink-3)',
              transition: 'transform 0.2s ease',
              transform: expanded ? 'rotate(180deg)' : 'rotate(0)',
            }}
          />
        </div>
      </div>

      {/* Row 2: Working on or labels */}
      <div className="agent-card-v2-body">
        {agent.status === 'busy' && agent.current_task_label ? (
          <div className="flex items-center gap-2">
            <span style={{ color: 'var(--ink-3)', fontSize: '0.75rem' }}>Working:</span>
            <Badge variant="warning" style={{ fontSize: '0.625rem', padding: '1px 8px' }}>
              {agent.current_task_label}
            </Badge>
            {agent.current_task_id && (
              <span className="font-mono" style={{ color: 'var(--ink-3)', fontSize: '0.6875rem' }}>
                {agent.current_task_id.slice(0, 8)}
              </span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 flex-wrap">
            {agent.labels.map((label) => (
              <Badge key={label} variant="muted" style={{ fontSize: '0.625rem', padding: '1px 7px' }}>
                {label}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Row 3: Stats */}
      <div className="agent-card-v2-stats">
        <span className="agent-card-v2-stat">
          <span className="agent-card-v2-stat-num">{agent.tasks_completed}</span> done
        </span>
        <span className="agent-card-v2-stat-sep" />
        <span className="agent-card-v2-stat">
          <span className="agent-card-v2-stat-num" style={agent.tasks_failed > 0 ? { color: 'var(--negative)' } : undefined}>
            {agent.tasks_failed}
          </span> err
        </span>
        <span className="agent-card-v2-stat-sep" />
        <span className="agent-card-v2-stat">
          <span className="agent-card-v2-stat-num">{uptime}</span> up
        </span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="agent-card-v2-detail" onClick={(e) => e.stopPropagation()}>
          <div className="agent-card-v2-detail-row">
            <span className="agent-card-v2-detail-label">Labels</span>
            <div className="flex items-center gap-1.5 flex-wrap">
              {agent.labels.map((label) => (
                <Badge key={label} variant="muted" style={{ fontSize: '0.625rem', padding: '1px 7px' }}>
                  {label}
                </Badge>
              ))}
            </div>
          </div>
          <div className="agent-card-v2-detail-row">
            <span className="agent-card-v2-detail-label">Started</span>
            <span className="agent-card-v2-detail-value">
              {new Date(agent.started_at).toLocaleString()}
            </span>
          </div>
          <div className="agent-card-v2-detail-row">
            <span className="agent-card-v2-detail-label">Last heartbeat</span>
            <span className="agent-card-v2-detail-value">
              {formatUptime(agent.last_heartbeat)} ago
            </span>
          </div>
          {agent.current_task_id && (
            <div className="agent-card-v2-detail-row">
              <span className="agent-card-v2-detail-label">Current task</span>
              <span className="font-mono agent-card-v2-detail-value">
                {agent.current_task_id.slice(0, 12)}...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function formatUptime(startedAt: string): string {
  const seconds = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
}
