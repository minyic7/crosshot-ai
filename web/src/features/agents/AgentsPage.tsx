import { useState } from 'react'
import { Bot } from 'lucide-react'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
import { useListAgentsQuery, useGetAgentLogsQuery } from '@/store/api'
import { AgentCard } from './AgentCard'

export function AgentsPage() {
  const { data: agents, isLoading } = useListAgentsQuery(undefined, {
    pollingInterval: 5000,
  })
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)

  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <Bot size={20} />
        <h1 className="text-xl font-semibold">Agents</h1>
      </div>

      {isLoading ? (
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="w-full h-48" />
          ))}
        </div>
      ) : agents && agents.length > 0 ? (
        <div className="stats-grid">
          {agents.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              onViewLogs={() => setSelectedAgent(agent.name)}
            />
          ))}
        </div>
      ) : (
        <p style={{ color: 'var(--foreground-subtle)' }}>No agents connected</p>
      )}

      {selectedAgent && (
        <AgentLogsModal
          agentName={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  )
}

function AgentLogsModal({ agentName, onClose }: { agentName: string; onClose: () => void }) {
  const { data, isLoading } = useGetAgentLogsQuery(
    { name: agentName, lines: 100 },
    { pollingInterval: 3000 },
  )

  return (
    <Modal open title={`Logs: ${agentName}`} onClose={onClose} className="logs-modal">
      <div className="logs-content">
        {isLoading ? (
          <p>Loading logs...</p>
        ) : data?.logs && data.logs.length > 0 ? (
          data.logs.map((line, i) => (
            <div key={i} className="font-mono text-xs">{line}</div>
          ))
        ) : (
          <p style={{ color: 'var(--foreground-subtle)' }}>No logs available</p>
        )}
      </div>
    </Modal>
  )
}
