import { useState, useEffect } from "react"
import { useMemo } from "react"
import {
  Bot,
  Play,
  Square,
  RotateCw,
  ScrollText,
  Plus,
  X,
  AlertCircle,
  Server,
  Brain,
  User,
  Cog,
  Filter,
} from "lucide-react"
import { usePollingApi } from "@/hooks/use-polling-api"
import { useApi } from "@/hooks/use-api"

// ─── Types ───

interface AgentContainer {
  id: string
  container_id: string
  name: string
  status: "running" | "stopped" | "error" | string
  docker_status: string
  agent_type: string
  platform: string
  image: string
  started_at: string | null
  uptime_seconds: number | null
  created_by: string
}

interface ContainerStats {
  cpu_percent: number
  memory_usage_mb: number
  memory_limit_mb: number
  memory_percent: number
  error?: string
}

interface AgentConfigItem {
  id: number
  name: string
  display_name: string
  agent_type: string
  platform: string
  description: string | null
  command: string
  environment: Record<string, string>
  cpu_limit: string
  memory_limit: string
  restart_policy: string
  created_at: string | null
}

// ─── Helpers ───

function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "--"
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return `${h}h ${m}m`
  }
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  return `${d}d ${h}h`
}

const AGENT_TYPE_META: Record<string, { label: string; icon: typeof Bot }> = {
  "human-simulation": { label: "Human Simulation", icon: User },
  "yizhi-crawler": { label: "AI Crawler (Yizhi)", icon: Brain },
  api: { label: "System", icon: Cog },
}

const PLATFORM_LABELS: Record<string, string> = {
  x: "X",
  xhs: "XHS",
  system: "System",
}

function getPlatformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] || platform.toUpperCase()
}

function getTypeLabel(agentType: string): string {
  return AGENT_TYPE_META[agentType]?.label || agentType
}

function getTypeIcon(agentType: string) {
  const Icon = AGENT_TYPE_META[agentType]?.icon || Bot
  return <Icon size={18} />
}

function groupContainers(
  containers: AgentContainer[]
): { type: string; items: AgentContainer[] }[] {
  const order = ["human-simulation", "yizhi-crawler", "api"]
  const groups = new Map<string, AgentContainer[]>()

  for (const c of containers) {
    const list = groups.get(c.agent_type) || []
    list.push(c)
    groups.set(c.agent_type, list)
  }

  // Sort groups by predefined order, unknowns at the end
  return Array.from(groups.entries())
    .sort(([a], [b]) => {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
    .map(([type, items]) => ({ type, items }))
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "running":
      return "agent-badge agent-badge-running"
    case "stopped":
      return "agent-badge agent-badge-stopped"
    case "error":
      return "agent-badge agent-badge-error"
    default:
      return "agent-badge agent-badge-stopped"
  }
}

// ─── AgentCard ───

function AgentCard({
  container,
  onStart,
  onStop,
  onRestart,
  onViewLogs,
}: {
  container: AgentContainer
  onStart: () => void
  onStop: () => void
  onRestart: () => void
  onViewLogs: () => void
}) {
  const isRunning = container.status === "running"

  const { data: stats } = usePollingApi<ContainerStats>(
    isRunning ? `/api/agents/containers/${container.container_id}/stats` : "",
    isRunning ? 10000 : 0
  )

  const [actionLoading, setActionLoading] = useState(false)

  const handleAction = (action: () => void) => {
    setActionLoading(true)
    action()
    setTimeout(() => setActionLoading(false), 2000)
  }

  return (
    <div className={`glass-card agent-page-card ${isRunning ? "agent-card-active" : ""}`}>
      {/* Header */}
      <div className="agent-card-header">
        <div className="agent-card-title-row">
          <div className={`status-dot ${isRunning ? "online" : "offline"}`} />
          <span className="agent-card-name">{container.name}</span>
        </div>
        <div className="agent-card-tags">
          <span className="code-tag">{container.platform.toUpperCase()}</span>
          <span className={statusBadgeClass(container.status)}>{container.status}</span>
          <span className="agent-type-tag">{container.agent_type}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="agent-stats">
        <div className="agent-stat">
          <span className="agent-stat-label">CPU</span>
          <span className="agent-stat-value">
            {isRunning && stats && !stats.error ? `${stats.cpu_percent}%` : "--"}
          </span>
        </div>
        <div className="agent-stat">
          <span className="agent-stat-label">Memory</span>
          <span className="agent-stat-value">
            {isRunning && stats && !stats.error
              ? `${stats.memory_usage_mb}MB`
              : "--"}
          </span>
        </div>
        <div className="agent-stat">
          <span className="agent-stat-label">Uptime</span>
          <span className="agent-stat-value">
            {formatUptime(container.uptime_seconds)}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="agent-card-actions">
        {isRunning ? (
          <button
            className="btn btn-outline btn-sm"
            onClick={() => handleAction(onStop)}
            disabled={actionLoading}
          >
            <Square size={13} /> Stop
          </button>
        ) : (
          <button
            className="btn btn-outline btn-sm btn-success"
            onClick={() => handleAction(onStart)}
            disabled={actionLoading}
          >
            <Play size={13} /> Start
          </button>
        )}
        <button
          className="btn btn-outline btn-sm"
          onClick={() => handleAction(onRestart)}
          disabled={actionLoading}
        >
          <RotateCw size={13} /> Restart
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onViewLogs}
        >
          <ScrollText size={13} /> Logs
        </button>
      </div>
    </div>
  )
}

// ─── LogsModal ───

function LogsModal({
  containerId,
  containerName,
  onClose,
}: {
  containerId: string
  containerName: string
  onClose: () => void
}) {
  const { data, loading, refetch } = useApi<{ logs: string }>(
    `/api/agents/containers/${containerId}/logs?tail=200`
  )

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [onClose])

  useEffect(() => {
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = ""
    }
  }, [])

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="logs-modal" onClick={(e) => e.stopPropagation()}>
        <div className="logs-modal-header">
          <h2>{containerName}</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button className="btn btn-ghost btn-icon" onClick={refetch}>
              <RotateCw size={16} />
            </button>
            <button className="detail-close" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </div>
        <pre className="logs-content">
          {loading ? "Loading logs..." : data?.logs || "No logs available."}
        </pre>
      </div>
    </div>
  )
}

// ─── CreateAgentModal ───

function CreateAgentModal({
  configs,
  onClose,
  onCreated,
}: {
  configs: AgentConfigItem[]
  onClose: () => void
  onCreated: () => void
}) {
  const [selectedConfig, setSelectedConfig] = useState<number | null>(null)
  const [instanceName, setInstanceName] = useState("")
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [onClose])

  useEffect(() => {
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = ""
    }
  }, [])

  const handleCreate = async () => {
    if (!selectedConfig || !instanceName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const res = await fetch("/api/agents/containers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config_id: selectedConfig,
          instance_name: instanceName.trim(),
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || "Failed to create agent")
      } else {
        onCreated()
        onClose()
      }
    } catch {
      setError("Network error")
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="create-agent-modal" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose}>
          <X size={18} />
        </button>
        <div className="detail-body">
          <h2 className="detail-title">Create New Agent</h2>

          <div className="create-agent-field">
            <label>Agent Type</label>
            <div className="create-agent-configs">
              {configs.map((c) => (
                <button
                  key={c.id}
                  className={`create-agent-config-card ${
                    selectedConfig === c.id ? "selected" : ""
                  }`}
                  onClick={() => {
                    setSelectedConfig(c.id)
                    if (!instanceName)
                      setInstanceName(`${c.name}-${Date.now() % 10000}`)
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="code-tag">{c.platform.toUpperCase()}</span>
                    <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>
                      {c.display_name}
                    </span>
                  </div>
                  {c.description && (
                    <span style={{ fontSize: "0.75rem", color: "var(--foreground-subtle)", marginTop: 2 }}>
                      {c.description}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="create-agent-field">
            <label>Instance Name</label>
            <input
              type="text"
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              placeholder="my-crawler-1"
              className="create-agent-input"
            />
          </div>

          {error && (
            <div className="create-agent-error">
              <AlertCircle size={14} /> {error}
            </div>
          )}

          <button
            className="topnav-cta"
            style={{ alignSelf: "flex-end", marginTop: 8 }}
            onClick={handleCreate}
            disabled={creating || !selectedConfig || !instanceName.trim()}
          >
            {creating ? "Creating..." : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ───

export function AgentsPage() {
  const {
    data: containers,
    loading,
    refetch,
  } = usePollingApi<AgentContainer[]>("/api/agents/containers", 5000)

  const { data: configs } = useApi<AgentConfigItem[]>("/api/agents/configs")

  const [logsTarget, setLogsTarget] = useState<{
    id: string
    name: string
  } | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [filterPlatform, setFilterPlatform] = useState<string>("all")
  const [filterType, setFilterType] = useState<string>("all")

  const runningCount =
    containers?.filter((c) => c.status === "running").length || 0
  const totalCount = containers?.length || 0

  const { platforms, types } = useMemo(() => {
    if (!containers) return { platforms: [], types: [] }
    const pSet = new Set<string>()
    const tSet = new Set<string>()
    for (const c of containers) {
      pSet.add(c.platform)
      tSet.add(c.agent_type)
    }
    const typeOrder = ["human-simulation", "yizhi-crawler", "api"]
    return {
      platforms: Array.from(pSet).sort(),
      types: Array.from(tSet).sort(
        (a, b) =>
          (typeOrder.indexOf(a) === -1 ? 999 : typeOrder.indexOf(a)) -
          (typeOrder.indexOf(b) === -1 ? 999 : typeOrder.indexOf(b))
      ),
    }
  }, [containers])

  const filtered = useMemo(() => {
    if (!containers) return []
    return containers.filter((c) => {
      if (filterPlatform !== "all" && c.platform !== filterPlatform) return false
      if (filterType !== "all" && c.agent_type !== filterType) return false
      return true
    })
  }, [containers, filterPlatform, filterType])

  const groups = useMemo(
    () => groupContainers(filtered),
    [filtered]
  )

  const containerAction = async (containerId: string, action: string) => {
    try {
      await fetch(`/api/agents/containers/${containerId}/${action}`, {
        method: "POST",
      })
      setTimeout(refetch, 1500)
    } catch (e) {
      console.error(`Action ${action} failed:`, e)
    }
  }

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Bot size={28} />
            Agents
          </h1>
          <p className="page-subtitle">Manage your crawler containers</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="live-badge">
            <span className="status-dot online" style={{ width: 8, height: 8 }} />
            {runningCount}/{totalCount} running
          </span>
          <button className="topnav-cta" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            New Agent
          </button>
        </div>
      </div>

      {/* Filters */}
      {!loading && containers && containers.length > 0 && (
        <div className="agent-filters">
          <div className="agent-filter-group">
            <Filter size={14} className="agent-filter-icon" />
            <div className="filter-tabs">
              <button
                className={`filter-tab ${filterPlatform === "all" ? "active" : ""}`}
                onClick={() => setFilterPlatform("all")}
              >
                All Platforms
              </button>
              {platforms.map((p) => (
                <button
                  key={p}
                  className={`filter-tab ${filterPlatform === p ? "active" : ""}`}
                  onClick={() => setFilterPlatform(p)}
                >
                  {getPlatformLabel(p)}
                </button>
              ))}
            </div>
          </div>
          <div className="agent-filter-group">
            <div className="filter-tabs">
              <button
                className={`filter-tab ${filterType === "all" ? "active" : ""}`}
                onClick={() => setFilterType("all")}
              >
                All Types
              </button>
              {types.map((t) => (
                <button
                  key={t}
                  className={`filter-tab ${filterType === t ? "active" : ""}`}
                  onClick={() => setFilterType(t)}
                >
                  {getTypeLabel(t)}
                </button>
              ))}
            </div>
          </div>
          {(filterPlatform !== "all" || filterType !== "all") && (
            <span className="agent-filter-count">
              {filtered.length} of {totalCount}
            </span>
          )}
        </div>
      )}

      {/* Agent Groups */}
      {loading ? (
        <div className="agents-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card agent-page-card agent-skeleton">
              <div className="skeleton skeleton-text" style={{ width: "70%" }} />
              <div
                className="skeleton skeleton-text-sm"
                style={{ width: "50%", marginTop: 12 }}
              />
              <div className="agent-stats" style={{ marginTop: "auto" }}>
                <div className="skeleton skeleton-number" />
                <div className="skeleton skeleton-number" />
                <div className="skeleton skeleton-number" />
              </div>
            </div>
          ))}
        </div>
      ) : !containers || containers.length === 0 ? (
        <div className="agents-empty">
          <Server size={32} style={{ color: "var(--foreground-subtle)" }} />
          <p>
            No managed containers found. Make sure Docker is running and
            containers have the <code>crosshot.managed</code> label.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="agents-empty">
          <Filter size={32} style={{ color: "var(--foreground-subtle)" }} />
          <p>No agents match the current filters.</p>
          <button
            className="btn btn-outline btn-sm"
            onClick={() => {
              setFilterPlatform("all")
              setFilterType("all")
            }}
          >
            Clear Filters
          </button>
        </div>
      ) : (
        <div className="agent-groups">
          {groups.map((group) => {
            const groupRunning = group.items.filter(
              (c) => c.status === "running"
            ).length
            return (
              <section key={group.type} className="agent-group">
                <div className="agent-group-header">
                  <div className="agent-group-title">
                    {getTypeIcon(group.type)}
                    <h2>{getTypeLabel(group.type)}</h2>
                  </div>
                  <span className="agent-group-count">
                    {groupRunning}/{group.items.length} running
                  </span>
                </div>
                <div className="agents-grid">
                  {group.items.map((c) => (
                    <AgentCard
                      key={c.container_id}
                      container={c}
                      onStart={() =>
                        containerAction(c.container_id, "start")
                      }
                      onStop={() =>
                        containerAction(c.container_id, "stop")
                      }
                      onRestart={() =>
                        containerAction(c.container_id, "restart")
                      }
                      onViewLogs={() =>
                        setLogsTarget({
                          id: c.container_id,
                          name: c.name,
                        })
                      }
                    />
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {/* Modals */}
      {logsTarget && (
        <LogsModal
          containerId={logsTarget.id}
          containerName={logsTarget.name}
          onClose={() => setLogsTarget(null)}
        />
      )}

      {showCreate && configs && (
        <CreateAgentModal
          configs={configs}
          onClose={() => setShowCreate(false)}
          onCreated={refetch}
        />
      )}
    </div>
  )
}
