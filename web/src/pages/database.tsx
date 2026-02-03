import { useState, useRef, useCallback, useEffect } from "react"
import { Database, HardDrive, CheckCircle, XCircle, AlertCircle, RefreshCw, ArrowUpRight } from "lucide-react"
import { useApi } from "@/hooks/use-api"
import { useCountUp } from "@/hooks/use-count-up"

interface TableStat {
  table: string
  count: number
  today: number
}

interface PlatformBreakdown {
  contents: Record<string, number>
  users: Record<string, number>
  comments: Record<string, number>
}

interface ScrapeHealth {
  total: number
  success: number
  failed: number
  success_rate: number
  avg_duration_ms: number
}

interface SearchTask {
  id: number
  keyword: string
  platform: string
  status: string
  contents_found: number
  created_at: string | null
}

interface StorageInfo {
  db_file_size_bytes: number
  db_file_size_mb: number
  data_dir_size_bytes: number
  data_dir_size_mb: number
  data_dir_file_count: number
  db_path: string
}

function AnimatedCount({ value }: { value: number }) {
  const animated = useCountUp(value.toLocaleString(), 800)
  return <>{animated}</>
}

function formatSize(mb: number): string {
  if (mb < 1) return `${Math.round(mb * 1024)} KB`
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(mb / 1024).toFixed(2)} GB`
}

const TABLE_LABELS: Record<string, string> = {
  users: "Users",
  contents: "Contents",
  comments: "Comments",
  content_history: "History",
  search_tasks: "Tasks",
  scrape_logs: "Scrape Logs",
  image_download_logs: "Media DL",
}

const TABLE_COLORS: Record<string, string> = {
  users: "icon-orange",
  contents: "icon-blue",
  comments: "icon-purple",
  content_history: "icon-teal",
  search_tasks: "icon-green",
  scrape_logs: "icon-lavender",
  image_download_logs: "icon-peach",
}

const PLATFORM_COLORS: Record<string, string> = {
  x: "#23272e",
  xhs: "#e84040",
}

/** Map table name → platform breakdown key */
const TABLE_TO_PLATFORM_KEY: Record<string, keyof PlatformBreakdown> = {
  users: "users",
  contents: "contents",
  comments: "comments",
}

function DonutPopover({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, v]) => sum + v, 0)
  if (total === 0) return null

  // Build conic-gradient stops
  let accumulated = 0
  const stops = entries.flatMap(([k, v]) => {
    const start = accumulated
    const pct = (v / total) * 100
    accumulated += pct
    const color = PLATFORM_COLORS[k] || "#ddd"
    return [`${color} ${start}%`, `${color} ${accumulated}%`]
  })

  return (
    <div className="donut-popover">
      <div
        className="donut-ring"
        style={{
          background: `conic-gradient(${stops.join(", ")})`,
        }}
      >
        <div className="donut-hole" />
      </div>
      <div className="donut-legend">
        {entries.map(([k, v]) => (
          <div key={k} className="donut-legend-item">
            <span className="donut-dot" style={{ background: PLATFORM_COLORS[k] || "#ddd" }} />
            <span className="donut-platform">{k.toUpperCase()}</span>
            <span className="donut-value">{v.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { className: string; icon: React.ReactNode }> = {
    running: { className: "badge-success", icon: <RefreshCw size={10} /> },
    completed: { className: "badge-muted", icon: <CheckCircle size={10} /> },
    failed: { className: "badge-error", icon: <XCircle size={10} /> },
    pending: { className: "badge-muted", icon: <AlertCircle size={10} /> },
  }
  const c = config[status] || config.pending
  return (
    <span className={`badge ${c.className}`} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {c.icon}
      {status}
    </span>
  )
}

const TIME_RANGES = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "1y", hours: 8760 },
  { label: "All", hours: null },
] as const

/** Horizontal pill tabs — snap-center, sliding underline, scroll-aware fades. */
function PlatformTabs({
  items,
  value,
  onChange,
}: {
  items: { label: string; value: string | null }[]
  value: string | null
  onChange: (v: string | null) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const underlineRef = useRef<HTMLDivElement>(null)
  const [fades, setFades] = useState({ left: false, right: false })

  // Update underline position whenever value changes
  useEffect(() => {
    const container = scrollRef.current
    const bar = underlineRef.current
    if (!container || !bar) return
    const active = container.querySelector<HTMLElement>(".platform-tab.active")
    if (active) {
      bar.style.width = `${active.offsetWidth}px`
      bar.style.transform = `translateX(${active.offsetLeft}px)`
    }
  }, [value, items])

  // Scroll-aware fade edges
  const updateFades = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setFades({
      left: el.scrollLeft > 4,
      right: el.scrollLeft < el.scrollWidth - el.clientWidth - 4,
    })
  }, [])

  useEffect(() => {
    updateFades()
  }, [items, updateFades])

  const handleScroll = useCallback(() => {
    updateFades()
  }, [updateFades])

  const handleClick = useCallback(
    (v: string | null, e: React.MouseEvent<HTMLButtonElement>) => {
      onChange(v)
      e.currentTarget.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" })
    },
    [onChange],
  )

  return (
    <div className="platform-tabs">
      {fades.left && <div className="platform-tabs-fade platform-tabs-fade-left" />}
      {fades.right && <div className="platform-tabs-fade platform-tabs-fade-right" />}
      <div className="platform-tabs-scroll" ref={scrollRef} onScroll={handleScroll}>
        <div className="platform-tabs-underline" ref={underlineRef} />
        {items.map((item) => (
          <button
            key={item.value ?? "__all"}
            className={`platform-tab ${item.value === value ? "active" : ""}`}
            onClick={(e) => handleClick(item.value, e)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function DatabasePage() {
  const [healthRange, setHealthRange] = useState<number | null>(24)
  const [healthPlatform, setHealthPlatform] = useState<string | null>(null)

  const healthParams = new URLSearchParams()
  if (healthRange !== null) healthParams.set("hours", String(healthRange))
  if (healthPlatform) healthParams.set("platform", healthPlatform)
  const healthQuery = healthParams.toString()

  const { data: tables, loading: tablesLoading, refetch: refetchTables } = useApi<TableStat[]>("/api/stats/tables")
  const { data: platforms } = useApi<PlatformBreakdown>("/api/stats/platforms")
  const { data: contentTypes, loading: typesLoading } = useApi<Record<string, number>>("/api/stats/content-types")
  const { data: scrapeHealth, loading: healthLoading } = useApi<ScrapeHealth>(`/api/stats/scrape-health${healthQuery ? `?${healthQuery}` : ""}`)
  const { data: searchTasks, loading: tasksLoading } = useApi<SearchTask[]>("/api/stats/search-tasks")
  const { data: storage, loading: storageLoading } = useApi<StorageInfo>("/api/stats/storage")

  const totalToday = tables?.reduce((sum, t) => sum + t.today, 0) || 0

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1>Database</h1>
          <p className="mt-2 text-base text-muted">
            System status and data overview
          </p>
        </div>
        <button className="btn btn-ghost" onClick={refetchTables} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Storage Info */}
      <div className="glass-card storage-card">
        <div className="storage-card-inner">
          <div className="storage-icon">
            <HardDrive size={20} />
          </div>
          <div className="storage-main">
            <div className="storage-row">
              <span className="storage-label">Database</span>
              <span className="storage-value">
                {storageLoading ? "..." : storage ? formatSize(storage.db_file_size_mb) : "-"}
              </span>
            </div>
            <div className="storage-row">
              <span className="storage-label">Data Directory</span>
              <span className="storage-value">
                {storageLoading ? "..." : storage ? `${formatSize(storage.data_dir_size_mb)} · ${storage.data_dir_file_count} files` : "-"}
              </span>
            </div>
            {storage && (
              <div className="storage-path">
                {storage.db_path}
              </div>
            )}
          </div>
          {totalToday > 0 && (
            <div className="storage-today">
              <ArrowUpRight size={12} />
              +{totalToday} rows today
            </div>
          )}
        </div>
      </div>

      {/* Table Overview — compact row with hover donut */}
      <div className="glass-card table-compact">
        {tablesLoading ? (
          <div className="table-compact-row">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="table-compact-item">
                <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }} />
                <div className="skeleton skeleton-text-sm" />
              </div>
            ))}
          </div>
        ) : (
          <div className="table-compact-row">
            {tables?.filter((t) => !["content_history", "search_tasks", "scrape_logs", "image_download_logs"].includes(t.table)).map((t) => {
              const platformKey = TABLE_TO_PLATFORM_KEY[t.table]
              const platformData = platformKey && platforms ? platforms[platformKey] : null
              return (
                <div key={t.table} className="table-compact-item has-popover">
                  <div className={`table-compact-icon ${TABLE_COLORS[t.table] || "icon-teal"}`}>
                    <Database size={12} />
                  </div>
                  <span className="table-compact-count"><AnimatedCount value={t.count} /></span>
                  <span className="table-compact-label">{TABLE_LABELS[t.table] || t.table}</span>
                  {t.today > 0 && (
                    <span className="table-compact-today">+{t.today}</span>
                  )}
                  {platformData && <DonutPopover data={platformData} />}
                </div>
              )
            })}
          </div>
        )}

        {/* Content type chips inline */}
        {!typesLoading && contentTypes && (
          <div className="type-chips-inline">
            {Object.entries(contentTypes)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <span key={k} className="type-chip">
                  {k} <strong>{v.toLocaleString()}</strong>
                </span>
              ))}
          </div>
        )}
      </div>

      {/* Two Column: Scrape Health + Search Tasks */}
      <div className="two-column">
        <div className="stack">
          <div className="section-header">
            <h2>Scrape Health</h2>
          </div>

          <div className="glass-card" style={{ padding: 24 }}>
            {/* Filters — two separate groups */}
            <div className="health-filters">
              <div className="filter-tabs">
                {TIME_RANGES.map((r) => (
                  <button
                    key={r.label}
                    className={`filter-tab ${healthRange === r.hours ? "active" : ""}`}
                    onClick={() => setHealthRange(r.hours)}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              {platforms && (
                <PlatformTabs
                  items={[
                    { label: "All", value: null },
                    ...[...new Set([
                      ...Object.keys(platforms.contents),
                      ...Object.keys(platforms.users),
                      ...Object.keys(platforms.comments),
                    ])].map((p) => ({ label: p.toUpperCase(), value: p })),
                    { label: "TikTok", value: "tiktok" },
                    { label: "Instagram", value: "instagram" },
                    { label: "YouTube", value: "youtube" },
                    { label: "Facebook", value: "facebook" },
                    { label: "LinkedIn", value: "linkedin" },
                    { label: "微博", value: "weibo" },
                    { label: "抖音", value: "douyin" },
                    { label: "B站", value: "bilibili" },
                  ]}
                  value={healthPlatform}
                  onChange={setHealthPlatform}
                />
              )}
            </div>

            {healthLoading ? (
              <div className="skeleton skeleton-number" style={{ marginTop: 16 }} />
            ) : scrapeHealth ? (
              <>
                <div className="health-hero">
                  <span className={`health-hero-value ${scrapeHealth.success_rate >= 80 ? "health-success" : scrapeHealth.success_rate >= 50 ? "" : "health-error"}`}>
                    {scrapeHealth.success_rate}%
                  </span>
                  <div className="health-hero-meta">
                    <span>{scrapeHealth.total} ops</span>
                    <span className="health-success">{scrapeHealth.success} ok</span>
                    <span className="health-error">{scrapeHealth.failed} fail</span>
                  </div>
                </div>
                <div style={{ marginTop: 12 }}>
                  <div className="bar-track" style={{ height: 6, borderRadius: 3 }}>
                    <div
                      className="bar-fill bar-success"
                      style={{
                        width: `${scrapeHealth.success_rate}%`,
                        height: "100%",
                        borderRadius: 3,
                      }}
                    />
                  </div>
                  <p className="text-xs text-muted" style={{ marginTop: 6 }}>
                    Avg {Math.round(scrapeHealth.avg_duration_ms)}ms
                  </p>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted" style={{ textAlign: "center", padding: "16px 0" }}>
                No data for this range.
              </p>
            )}
          </div>
        </div>

        <div className="stack">
          <div className="section-header">
            <h2>Recent Search Tasks</h2>
          </div>

          {tasksLoading ? (
            <div className="glass-card" style={{ padding: 24 }}>
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-text" style={{ marginTop: 12 }} />
            </div>
          ) : searchTasks && searchTasks.length > 0 ? (
            <div className="glass-card-static" style={{ overflow: "hidden" }}>
              <div className="task-list">
                {searchTasks.slice(0, 8).map((task) => (
                  <div key={task.id} className="task-item">
                    <div className="flex items-center gap-3" style={{ minWidth: 0 }}>
                      <span className="code-tag" style={{ flexShrink: 0 }}>{task.platform.toUpperCase()}</span>
                      <span className="text-sm" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {task.keyword}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted">{task.contents_found} found</span>
                      <StatusBadge status={task.status} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="glass-card" style={{ padding: 24, textAlign: "center" }}>
              <p className="text-sm text-muted">No search tasks yet.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
