import { FileText, MessageSquare, Users, TrendingUp, Play, Square, ArrowUpRight, Clock, ChevronRight, Sparkles, Hash, Activity } from "lucide-react"
import { useCountUp } from "@/hooks/use-count-up"
import { useApi } from "@/hooks/use-api"

interface OverviewData {
  total_contents: number
  total_comments: number
  total_users: number
  total_tasks: number
  today_contents: number
  today_comments: number
  today_users: number
}

interface SearchTask {
  id: number
  keyword: string
  platform: string
  status: string
  contents_found: number
  comments_scraped: number
  users_discovered: number
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

interface ActivityItem {
  id: number
  task_type: string
  target_id: string
  platform: string
  status: string
  items_count: number
  duration_ms: number
  error_message: string | null
  created_at: string | null
}

function AnimatedValue({ value }: { value: string }) {
  const animated = useCountUp(value, 900)
  return <>{animated}</>
}

function formatNumber(n: number): string {
  return n.toLocaleString()
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "-"
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function activityDescription(item: ActivityItem): string {
  if (item.status === "failed") {
    return `Failed: ${item.task_type} ${item.error_message || ""}`
  }
  const typeLabel = item.task_type === "search" ? "posts" : item.task_type === "comments" ? "comments" : "users"
  return `Scraped ${item.items_count} ${typeLabel}`
}

function StatSkeleton() {
  return (
    <div className="glass-card stat-card">
      <div className="stat-header">
        <div className="stat-header-left">
          <div className="skeleton skeleton-icon" />
          <div className="skeleton skeleton-text" />
        </div>
      </div>
      <div className="skeleton skeleton-number" style={{ marginTop: "auto" }} />
    </div>
  )
}

export function Dashboard() {
  const { data: overview, loading: overviewLoading } = useApi<OverviewData>("/api/stats/overview")
  const { data: tasks, loading: tasksLoading } = useApi<SearchTask[]>("/api/stats/search-tasks")
  const { data: activity, loading: activityLoading } = useApi<ActivityItem[]>("/api/stats/activity")

  const stats = overview ? [
    { label: "Total Contents", value: formatNumber(overview.total_contents), change: `+${overview.today_contents} today`, icon: <FileText size={18} />, color: "icon-blue" },
    { label: "Today's New", value: formatNumber(overview.today_contents + overview.today_comments + overview.today_users), change: "today", icon: <TrendingUp size={18} />, color: "icon-green" },
    { label: "Comments", value: formatNumber(overview.total_comments), change: `+${overview.today_comments} today`, icon: <MessageSquare size={18} />, color: "icon-purple" },
    { label: "Authors", value: formatNumber(overview.total_users), change: `+${overview.today_users} today`, icon: <Users size={18} />, color: "icon-orange" },
  ] : []

  const runningTasks = tasks?.filter((t) => t.status === "running") || []
  const recentTasks = tasks?.slice(0, 4) || []

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="mt-2 text-base text-muted">
            Real-time overview of your AI crawlers
          </p>
        </div>
        <span className="last-updated">
          <Clock size={12} />
          Updated just now
        </span>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        {overviewLoading ? (
          <>
            <StatSkeleton />
            <StatSkeleton />
            <StatSkeleton />
            <StatSkeleton />
          </>
        ) : stats.map((stat) => (
          <div key={stat.label} className="glass-card stat-card">
            <div className="stat-header">
              <div className="stat-header-left">
                <div className={`stat-icon ${stat.color}`}>
                  {stat.icon}
                </div>
                <span className="stat-label">{stat.label}</span>
              </div>
              <span className="stat-change">
                <ArrowUpRight size={10} />
                {stat.change}
              </span>
            </div>
            <div className="stat-value"><AnimatedValue value={stat.value} /></div>
          </div>
        ))}
      </div>

      {/* Two Column Layout */}
      <div className="two-column">
        {/* Search Tasks Section */}
        <div className="stack">
          <div className="section-header">
            <h2>Search Tasks</h2>
            <span className="text-sm text-muted">
              {runningTasks.length} running
            </span>
          </div>
          <div className="stack">
            {tasksLoading ? (
              <div className="glass-card agent-card">
                <div className="skeleton skeleton-text" style={{ width: "70%" }} />
                <div className="skeleton skeleton-text-sm" style={{ width: "50%", marginTop: 12 }} />
              </div>
            ) : recentTasks.length === 0 ? (
              <div className="glass-card agent-card">
                <p className="text-sm text-muted" style={{ textAlign: "center", padding: "24px 0" }}>
                  No search tasks yet. Start a crawler to see tasks here.
                </p>
              </div>
            ) : recentTasks.map((task) => (
              <div key={task.id} className="glass-card agent-card">
                <div className="flex items-start justify-between">
                  <div className="stack-sm">
                    <div className="flex items-center gap-3">
                      <div className={`status-dot ${task.status === "running" ? "online" : "offline"}`} />
                      <span className="text-base font-semibold">{task.platform.toUpperCase()}</span>
                      <span className={`badge ${task.status === "running" ? "badge-success" : task.status === "completed" ? "badge-muted" : task.status === "failed" ? "badge-error" : "badge-muted"}`}>
                        {task.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted">Keyword:</span>
                      <span className="code-tag">{task.keyword}</span>
                    </div>
                  </div>
                  <button className="btn btn-outline btn-icon">
                    {task.status === "running" ? <Square size={18} /> : <Play size={18} />}
                  </button>
                </div>
                <div className="agent-stats" style={{ marginTop: 'auto' }}>
                  <div>
                    <div className="agent-stat-label">Found</div>
                    <div className="agent-stat-value">{task.contents_found}</div>
                  </div>
                  <div>
                    <div className="agent-stat-label">Comments</div>
                    <div className="agent-stat-value">{task.comments_scraped}</div>
                  </div>
                  <div>
                    <div className="agent-stat-label">Created</div>
                    <div className="agent-stat-value">{timeAgo(task.created_at)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="stack">
          <div className="section-header">
            <h2>Recent Activity</h2>
            <span className="live-badge">
              <span className="live-dot" />
              Live
            </span>
          </div>
          <div className="glass-card-static" style={{ overflow: 'hidden' }}>
            <div className="activity-list" style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {activityLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="activity-item">
                    <div className="skeleton skeleton-circle" />
                    <div className="flex-1">
                      <div className="skeleton skeleton-text" />
                      <div className="skeleton skeleton-text-sm" style={{ marginTop: 6 }} />
                    </div>
                  </div>
                ))
              ) : !activity || activity.length === 0 ? (
                <div style={{ padding: "24px 16px", textAlign: "center" }}>
                  <p className="text-sm text-muted">No activity yet.</p>
                </div>
              ) : activity.map((item) => (
                <div key={item.id} className="activity-item">
                  <div className={`activity-dot ${item.status === "failed" ? "activity-dot-error" : ""}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{activityDescription(item)}</p>
                    <p className="mt-1 text-xs text-muted">
                      <span className="font-medium">{item.platform?.toUpperCase()}</span>
                      <span className="mx-1.5 opacity-40">·</span>
                      <span className="font-mono">{item.target_id}</span>
                    </p>
                  </div>
                  <span className="font-mono text-xs text-subtle">
                    {timeAgo(item.created_at)}
                  </span>
                </div>
              ))}
            </div>
            <div className="view-all-link">
              View all activity
              <ChevronRight size={14} style={{ marginLeft: 4 }} />
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions / AI Suggestions */}
      <div className="suggestions-grid">
        <div className="suggestion-card">
          <div className="suggestion-card-icon icon-teal">
            <Sparkles size={16} />
          </div>
          <h3>Suggested Keyword</h3>
          <p>2026秋季穿搭趋势</p>
          <span className="suggestion-card-action">
            Start Crawling
            <ChevronRight size={12} />
          </span>
        </div>
        <div className="suggestion-card">
          <div className="suggestion-card-icon icon-lavender">
            <Hash size={16} />
          </div>
          <h3>Trending Topic</h3>
          <p>#AIFashion2026</p>
          <span className="suggestion-card-action">
            Add to Watch
            <ChevronRight size={12} />
          </span>
        </div>
        <div className="suggestion-card">
          <div className="suggestion-card-icon icon-peach">
            <Activity size={16} />
          </div>
          <h3>Agent Health</h3>
          <p>{overview ? `${overview.total_tasks} tasks tracked` : "Loading..."}</p>
          <span className="suggestion-card-action">
            View Details
            <ChevronRight size={12} />
          </span>
        </div>
      </div>
    </div>
  )
}
