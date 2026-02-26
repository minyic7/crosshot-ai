import { useState } from 'react'
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListAgentsQuery, useListQueuesQuery, useListTasksQuery, useListTaskLabelsQuery } from '@/store/api'
import { AgentCard } from './AgentCard'
import { TaskLine } from './TaskLine'
import { SubmitTaskModal } from './SubmitTaskModal'

const PAGE_SIZE = 30

const STATUS_OPTIONS: { value: string | undefined; label: string }[] = [
  { value: undefined, label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const STATUS_VARIANT: Record<string, 'warning' | 'success' | 'error' | 'muted'> = {
  pending: 'muted',
  running: 'warning',
  completed: 'success',
  failed: 'error',
}

export function AgentsPage() {
  const [submitOpen, setSubmitOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [labelFilter, setLabelFilter] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(0)

  const { data: agents, isLoading: agentsLoading } = useListAgentsQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: queues } = useListQueuesQuery(undefined, {
    pollingInterval: 5000,
  })
  const { data: labelsData } = useListTaskLabelsQuery(undefined, {
    pollingInterval: 10000,
  })

  const queryParams = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(labelFilter ? { label: labelFilter } : {}),
  }
  const { data: tasksData, isLoading: tasksLoading } = useListTasksQuery(queryParams, {
    pollingInterval: 5000,
  })

  const tasks = tasksData?.tasks ?? []
  const totalTasks = tasksData?.total ?? 0
  const totalPages = Math.ceil(totalTasks / PAGE_SIZE)
  const totalPending = queues?.reduce((sum, q) => sum + q.pending, 0) ?? 0

  // Build label options from labels data
  const labelOptions: { value: string | undefined; label: string; counts: Record<string, number> }[] = [
    { value: undefined, label: 'All', counts: {} },
  ]
  if (labelsData?.labels) {
    for (const [lbl, counts] of Object.entries(labelsData.labels)) {
      labelOptions.push({ value: lbl, label: lbl, counts })
    }
  }

  function handleStatusFilter(value: string | undefined) {
    setStatusFilter(value)
    setPage(0)
  }
  function handleLabelFilter(value: string | undefined) {
    setLabelFilter(value)
    setPage(0)
  }

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
            <span className="text-xs" style={{ color: 'var(--ink-3)' }}>
              {totalTasks} total
            </span>
          </div>
          <button
            className="btn btn-accent btn-sm"
            onClick={() => setSubmitOpen(true)}
          >
            <Plus size={14} />
            Submit
          </button>
        </div>

        {/* Filters */}
        <div className="task-queue-filters">
          <div className="task-queue-filter-group">
            <span className="task-queue-filter-label">Status</span>
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value ?? 'all'}
                className={`task-queue-chip${statusFilter === opt.value ? ' task-queue-chip-active' : ''}`}
                onClick={() => handleStatusFilter(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {labelOptions.length > 1 && (
            <div className="task-queue-filter-group">
              <span className="task-queue-filter-label">Label</span>
              {labelOptions.map((opt) => (
                <button
                  key={opt.value ?? 'all'}
                  className={`task-queue-chip${labelFilter === opt.value ? ' task-queue-chip-active' : ''}`}
                  onClick={() => handleLabelFilter(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="task-queue-list">
          {tasksLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="w-full h-10" />
            ))
          ) : tasks.length > 0 ? (
            tasks.map((task) => (
              <TaskLine key={task.id} task={task} />
            ))
          ) : (
            <p className="py-6 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
              No tasks found
            </p>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="task-queue-pagination">
            <button
              className="task-queue-page-btn"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              <ChevronLeft size={14} />
            </button>
            <span className="task-queue-page-info">
              {page + 1} / {totalPages}
            </span>
            <button
              className="task-queue-page-btn"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      <SubmitTaskModal open={submitOpen} onClose={() => setSubmitOpen(false)} />
    </div>
  )
}
