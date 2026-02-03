import { FileText, MessageSquare, Users, TrendingUp, Play, Square, ArrowUpRight, Clock, ChevronRight, Sparkles, Hash, Activity } from "lucide-react"
import { useCountUp } from "@/hooks/use-count-up"

// Mock data
const stats = [
  { label: "Total Contents", value: "1,284", change: "+12%", icon: <FileText size={18} />, color: "icon-blue" },
  { label: "Today's New", value: "47", change: "+8%", icon: <TrendingUp size={18} />, color: "icon-green" },
  { label: "Comments", value: "328", change: "+15%", icon: <MessageSquare size={18} />, color: "icon-purple" },
  { label: "Authors", value: "156", change: "+5%", icon: <Users size={18} />, color: "icon-orange" },
]

function AnimatedValue({ value }: { value: string }) {
  const animated = useCountUp(value, 900)
  return <>{animated}</>
}

const agents = [
  { id: 1, name: "X Crawler", platform: "X", status: "running", keyword: "2026穿搭女", collected: 847, lastRun: "2 min ago" },
  { id: 2, name: "XHS Crawler", platform: "XHS", status: "stopped", keyword: "春季穿搭", collected: 437, lastRun: "1 hour ago" },
]

const recentActivity = [
  { time: "2m", action: "Saved 3 new posts", platform: "X", keyword: "2026穿搭女" },
  { time: "5m", action: "AI skipped 2 low-quality posts", platform: "X", keyword: "2026穿搭女" },
  { time: "8m", action: "Fetched 12 comments", platform: "X", keyword: "#Clawbot" },
  { time: "15m", action: "Agent started", platform: "X", keyword: "2026穿搭女" },
  { time: "20m", action: "Saved 5 new posts", platform: "XHS", keyword: "春季穿搭" },
]

export function Dashboard() {
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
          Updated 2 min ago
        </span>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        {stats.map((stat) => (
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
        {/* Agents Section */}
        <div className="stack">
          <div className="section-header">
            <h2>Active Agents</h2>
            <button className="btn btn-ghost">View all</button>
          </div>
          <div className="stack">
            {agents.map((agent) => (
              <div key={agent.id} className="glass-card agent-card">
                <div className="flex items-start justify-between">
                  <div className="stack-sm">
                    <div className="flex items-center gap-3">
                      <div className={`status-dot ${agent.status === "running" ? "online" : "offline"}`} />
                      <span className="text-base font-semibold">{agent.name}</span>
                      <span className={`badge ${agent.status === "running" ? "badge-success" : "badge-muted"}`}>
                        {agent.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted">Keyword:</span>
                      <span className="code-tag">{agent.keyword}</span>
                    </div>
                  </div>
                  <button className="btn btn-outline btn-icon">
                    {agent.status === "running" ? <Square size={18} /> : <Play size={18} />}
                  </button>
                </div>
                <div className="agent-stats" style={{ marginTop: 'auto' }}>
                  <div>
                    <div className="agent-stat-label">Collected</div>
                    <div className="agent-stat-value">{agent.collected}</div>
                  </div>
                  <div>
                    <div className="agent-stat-label">Last run</div>
                    <div className="agent-stat-value">{agent.lastRun}</div>
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
              {recentActivity.map((activity, i) => (
                <div key={i} className="activity-item">
                  <div className="activity-dot" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{activity.action}</p>
                    <p className="mt-1 text-xs text-muted">
                      <span className="font-medium">{activity.platform}</span>
                      <span className="mx-1.5 opacity-40">·</span>
                      <span className="font-mono">{activity.keyword}</span>
                    </p>
                  </div>
                  <span className="font-mono text-xs text-subtle">
                    {activity.time}
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
          <p>All 2 agents running normally</p>
          <span className="suggestion-card-action">
            View Details
            <ChevronRight size={12} />
          </span>
        </div>
      </div>
    </div>
  )
}
