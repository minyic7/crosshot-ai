import { useState } from 'react'
import { Plus, ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListAgentsQuery, useListQueuesQuery, useListTasksQuery } from '@/store/api'
import { AgentCard } from './AgentCard'
import { TaskLine } from './TaskLine'
import { SubmitTaskModal } from './SubmitTaskModal'

export function AgentsPage() {
  const [submitOpen, setSubmitOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  const { data: agents, isLoading: agentsLoading } = useListAgentsQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: queues } = useListQueuesQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: tasksData, isLoading: tasksLoading } = useListTasksQuery(
    { limit: 30 },
    { pollingInterval: 5000 },
  )

  const tasks = tasksData?.tasks ?? []
  const activeTasks = tasks.filter(t => t.status === 'pending' || t.status === 'running')
  const historyTasks = tasks.filter(t => t.status === 'completed' || t.status === 'failed')
  const totalPending = queues?.reduce((sum, q) => sum + q.pending, 0) ?? 0

  return (
    <div className="stack">
      {/* Agent Cards */}
      {agentsLoading ? (
        <div className="agents-grid-v2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="w-full h-[120px] rounded-[14px]" />
          ))}
        </div>
      ) : agents && agents.length > 0 ? (
        <div className="agents-grid-v2">
          {agents.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <p style={{ color: 'var(--ink-3)' }}>No agents connected</p>
        </div>
      )}

      {/* Task Queue */}
      <div className="task-queue-section">
        <div className="task-queue-header">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold">Task Queue</h2>
            {totalPending > 0 && (
              <Badge variant="warning" style={{ fontSize: '0.625rem', padding: '1px 8px' }}>
                {totalPending} pending
              </Badge>
            )}
            {queues && queues.filter(q => q.pending > 0).map(q => (
              <span key={q.label} className="text-xs" style={{ color: 'var(--ink-3)' }}>
                {q.label}: {q.pending}
              </span>
            ))}
          </div>
          <button
            className="btn btn-accent btn-sm"
            onClick={() => setSubmitOpen(true)}
          >
            <Plus size={14} />
            Submit
          </button>
        </div>

        <div className="task-queue-list">
          {tasksLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="w-full h-10" />
            ))
          ) : tasks.length > 0 ? (
            <>
              {activeTasks.length > 0 && (
                <div className="task-queue-group">
                  {activeTasks.map((task) => (
                    <TaskLine key={task.id} task={task} />
                  ))}
                </div>
              )}
              {historyTasks.length > 0 && (
                <>
                  <div
                    className="task-queue-divider"
                    onClick={() => setHistoryOpen(!historyOpen)}
                  >
                    <ChevronDown
                      size={14}
                      style={{
                        color: 'var(--ink-3)',
                        transition: 'transform 0.2s ease',
                        transform: historyOpen ? 'rotate(0)' : 'rotate(-90deg)',
                        flexShrink: 0,
                      }}
                    />
                    <span>History</span>
                    <span className="task-queue-divider-count">{historyTasks.length}</span>
                  </div>
                  {historyOpen && (
                    <div className="task-queue-group task-queue-history">
                      {historyTasks.map((task) => (
                        <TaskLine key={task.id} task={task} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          ) : (
            <p className="py-6 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
              No tasks yet
            </p>
          )}
        </div>
      </div>

      <SubmitTaskModal open={submitOpen} onClose={() => setSubmitOpen(false)} />
    </div>
  )
}
