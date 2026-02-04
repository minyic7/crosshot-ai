import { useState, useEffect, useCallback } from "react"
import { Database, HardDrive, RefreshCw, ArrowUpRight, Heart, MessageCircle, Bookmark, X, ExternalLink, MapPin, ThumbsUp, Users } from "lucide-react"
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

interface StorageInfo {
  db_file_size_bytes: number
  db_file_size_mb: number
  data_dir_size_bytes: number
  data_dir_size_mb: number
  data_dir_file_count: number
  db_path: string
}

interface ContentAuthor {
  nickname: string | null
  avatar_url: string | null
  platform: string
}

interface ContentCard {
  id: number
  title: string | null
  content_text: string | null
  content_type: string
  cover_url: string | null
  platform: string
  likes: number
  collects: number
  comments: number
  publish_time: string | null
  created_at: string | null
  author: ContentAuthor | null
}

interface ContentListResponse {
  items: ContentCard[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

interface ContentDetailComment {
  id: number
  text: string
  likes: number
  ip_location: string | null
  created_at: string | null
  user_nickname: string | null
}

interface ContentDetailAuthor {
  nickname: string | null
  avatar_url: string | null
  description: string | null
  platform: string
  fans_count: string
  ip_location: string | null
}

interface ContentDetail {
  id: number
  title: string | null
  content_text: string | null
  content_type: string
  cover_url: string | null
  content_url: string | null
  platform: string
  platform_content_id: string
  likes: number
  likes_display: string
  collects: number
  collects_display: string
  comments_count: number
  comments_display: string
  image_urls: string[]
  video_urls: string[]
  publish_time: string | null
  created_at: string | null
  author: ContentDetailAuthor | null
  comments: ContentDetailComment[]
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

function timeAgo(isoString: string | null): string {
  if (!isoString) return ""
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return `${Math.floor(days / 30)}mo ago`
}

function formatCount(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function ContentMasonryCard({ card, index, onClick }: { card: ContentCard; index: number; onClick: () => void }) {
  return (
    <div className="masonry-card" style={{ animationDelay: `${(index % 20) * 60}ms`, cursor: "pointer" }} onClick={onClick}>
      {/* Header */}
      <div className="masonry-card-header">
        <span className="code-tag" style={{ flexShrink: 0 }}>{card.platform.toUpperCase()}</span>
        <span className="masonry-card-title">{card.title || "Untitled"}</span>
      </div>

      {/* Body: Image or Text */}
      {card.cover_url ? (
        <div className="masonry-card-image-wrap">
          <img src={card.cover_url} alt={card.title || ""} className="masonry-card-image" loading="lazy" />
        </div>
      ) : (
        <div className="masonry-card-text-body">
          <p>{card.content_text || "No content available."}</p>
        </div>
      )}

      {/* Stats row */}
      <div className="masonry-card-stats">
        <span className="masonry-stat"><Heart size={12} /> {formatCount(card.likes)}</span>
        <span className="masonry-stat"><MessageCircle size={12} /> {formatCount(card.comments)}</span>
        <span className="masonry-stat"><Bookmark size={12} /> {formatCount(card.collects)}</span>
      </div>

      {/* Footer */}
      <div className="masonry-card-footer">
        <span className="masonry-card-author">
          {card.author?.nickname || "Anonymous"}
        </span>
        <span className="masonry-card-time">{timeAgo(card.created_at)}</span>
      </div>
    </div>
  )
}

function ContentDetailModal({ contentId, onClose }: { contentId: number; onClose: () => void }) {
  const { data: detail, loading } = useApi<ContentDetail>(`/api/stats/content/${contentId}`)

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [onClose])

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = "" }
  }, [])

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Close button */}
        <button className="detail-close" onClick={onClose}>
          <X size={18} />
        </button>

        {loading ? (
          <div className="detail-loading">
            <div className="skeleton" style={{ width: "100%", height: 240, borderRadius: 0 }} />
            <div style={{ padding: 24 }}>
              <div className="skeleton skeleton-text" style={{ width: "70%" }} />
              <div className="skeleton skeleton-text" style={{ width: "90%", marginTop: 12 }} />
              <div className="skeleton skeleton-text" style={{ width: "50%", marginTop: 12 }} />
            </div>
          </div>
        ) : detail ? (
          <>
            {/* Cover image */}
            {detail.cover_url && (
              <div className="detail-cover">
                <img src={detail.cover_url} alt={detail.title || ""} />
              </div>
            )}

            <div className="detail-body">
              {/* Platform + title */}
              <div className="detail-header">
                <span className="code-tag">{detail.platform.toUpperCase()}</span>
                <span className="detail-type">{detail.content_type}</span>
                {detail.content_url && (
                  <a href={detail.content_url} target="_blank" rel="noopener noreferrer" className="detail-link">
                    <ExternalLink size={12} /> Source
                  </a>
                )}
              </div>
              <h2 className="detail-title">{detail.title || "Untitled"}</h2>

              {/* Content text */}
              {detail.content_text && (
                <p className="detail-text">{detail.content_text}</p>
              )}

              {/* Stats bar */}
              <div className="detail-stats">
                <span className="detail-stat">
                  <Heart size={14} /> {detail.likes_display}
                </span>
                <span className="detail-stat">
                  <MessageCircle size={14} /> {detail.comments_display}
                </span>
                <span className="detail-stat">
                  <Bookmark size={14} /> {detail.collects_display}
                </span>
              </div>

              {/* Author */}
              {detail.author && (
                <div className="detail-author-card">
                  <div className="detail-author-info">
                    <span className="detail-author-name">{detail.author.nickname || "Anonymous"}</span>
                    {detail.author.description && (
                      <span className="detail-author-desc">{detail.author.description}</span>
                    )}
                  </div>
                  <div className="detail-author-meta">
                    {detail.author.fans_count !== "0" && (
                      <span className="detail-meta-item"><Users size={12} /> {detail.author.fans_count} fans</span>
                    )}
                    {detail.author.ip_location && (
                      <span className="detail-meta-item"><MapPin size={12} /> {detail.author.ip_location}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="detail-metadata">
                {detail.publish_time && (
                  <span>Published: {new Date(detail.publish_time).toLocaleDateString()}</span>
                )}
                {detail.created_at && (
                  <span>Scraped: {timeAgo(detail.created_at)}</span>
                )}
                <span>ID: {detail.platform_content_id}</span>
              </div>

              {/* Comments */}
              {detail.comments.length > 0 && (
                <div className="detail-comments">
                  <h3>Comments ({detail.comments.length})</h3>
                  <div className="detail-comments-list">
                    {detail.comments.map((cm) => (
                      <div key={cm.id} className="detail-comment">
                        <div className="detail-comment-header">
                          <span className="detail-comment-author">{cm.user_nickname || "Anonymous"}</span>
                          <span className="detail-comment-time">{timeAgo(cm.created_at)}</span>
                        </div>
                        <p className="detail-comment-text">{cm.text}</p>
                        <div className="detail-comment-footer">
                          {cm.likes > 0 && (
                            <span className="detail-comment-likes"><ThumbsUp size={10} /> {cm.likes}</span>
                          )}
                          {cm.ip_location && (
                            <span className="detail-comment-location"><MapPin size={10} /> {cm.ip_location}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ padding: 48, textAlign: "center" }}>
            <p className="text-sm text-muted">Content not found.</p>
          </div>
        )}
      </div>
    </div>
  )
}

const TIME_RANGES = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "1y", hours: 8760 },
  { label: "All", hours: null },
] as const

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
  const { data: storage, loading: storageLoading } = useApi<StorageInfo>("/api/stats/storage")

  const totalToday = tables?.reduce((sum, t) => sum + t.today, 0) || 0

  // Content gallery — paginated masonry wall with sort/filter
  const [contentPage, setContentPage] = useState(1)
  const [contentSort, setContentSort] = useState<string>("newest")
  const [contentPlatform, setContentPlatform] = useState<string | null>(null)

  const contentParams = new URLSearchParams()
  contentParams.set("page", String(contentPage))
  contentParams.set("limit", "20")
  contentParams.set("sort", contentSort)
  if (contentPlatform) contentParams.set("platform", contentPlatform)

  const { data: contentList, loading: contentLoading } = useApi<ContentListResponse>(
    `/api/stats/content/list?${contentParams.toString()}`
  )
  const [allCards, setAllCards] = useState<ContentCard[]>([])

  useEffect(() => {
    if (contentList?.items) {
      setAllCards((prev) =>
        contentPage === 1 ? contentList.items : [...prev, ...contentList.items]
      )
    }
  }, [contentList, contentPage])

  // Reset pagination when sort or platform filter changes
  const handleContentSort = (sort: string) => {
    setContentSort(sort)
    setContentPage(1)
    setAllCards([])
  }
  const handleContentPlatform = (p: string | null) => {
    setContentPlatform(p)
    setContentPage(1)
    setAllCards([])
  }

  // Content detail modal
  const [selectedContentId, setSelectedContentId] = useState<number | null>(null)
  const closeDetail = useCallback(() => setSelectedContentId(null), [])

  // Health tier
  const healthTier = scrapeHealth
    ? scrapeHealth.success_rate >= 80
      ? "healthy"
      : scrapeHealth.success_rate >= 50
        ? "warning"
        : "critical"
    : "healthy"
  const healthLabel = healthTier === "healthy" ? "Healthy" : healthTier === "warning" ? "Warning" : "Critical"

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

      {/* Scrape Health — 3-column panel */}
      <div className="glass-card scrape-health-panel">
        {healthLoading ? (
          <div className="scrape-health-loading">
            <div className="skeleton" style={{ width: 110, height: 110, borderRadius: "50%" }} />
            <div className="health-metrics-2x2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="metric-square metric-square-gray">
                  <div className="skeleton skeleton-number" />
                </div>
              ))}
            </div>
            <div className="skeleton" style={{ width: "100%", height: 60, borderRadius: 8 }} />
          </div>
        ) : scrapeHealth ? (
          <>
            {/* Left: Health Score Circle */}
            <div className="health-score-col">
              <div className={`health-score-circle ${healthTier}`}>
                <span className="health-score-number">
                  <AnimatedCount value={scrapeHealth.success_rate} />%
                </span>
              </div>
              <span className={`health-score-label ${healthTier}`}>{healthLabel}</span>
              <span className="health-score-subtitle">
                {healthRange ? `Last ${TIME_RANGES.find(r => r.hours === healthRange)?.label}` : "All time"} performance
              </span>
            </div>

            {/* Middle: 2x2 Metric Grid */}
            <div className="health-metrics-2x2">
              <div className="metric-square metric-square-blue">
                <span className="metric-square-value">{scrapeHealth.total}</span>
                <span className="metric-square-label">Total Ops</span>
              </div>
              <div className="metric-square metric-square-green">
                <span className="metric-square-value">{scrapeHealth.success}</span>
                <span className="metric-square-label">Success</span>
              </div>
              <div className="metric-square metric-square-red">
                <span className="metric-square-value">{scrapeHealth.failed}</span>
                <span className="metric-square-label">Failed</span>
              </div>
              <div className="metric-square metric-square-gray">
                <span className="metric-square-value">
                  {scrapeHealth.avg_duration_ms > 0 ? Math.round(scrapeHealth.avg_duration_ms) : "—"}
                </span>
                <span className="metric-square-label">Avg ms</span>
              </div>
            </div>

            {/* Right: Filters + Platform tags */}
            <div className="health-filters-col">
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
              <div className="platform-tag-list">
                <button
                  className={`platform-tag ${healthPlatform === null ? "active" : ""}`}
                  onClick={() => setHealthPlatform(null)}
                >
                  All
                </button>
                {platforms && [...new Set([
                  ...Object.keys(platforms.contents),
                  ...Object.keys(platforms.users),
                  ...Object.keys(platforms.comments),
                ])].map((p) => (
                  <button
                    key={p}
                    className={`platform-tag ${healthPlatform === p ? "active" : ""}`}
                    onClick={() => setHealthPlatform(p)}
                  >
                    {p.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: "24px 0" }}>
            <p className="text-sm text-muted">No scrape data available.</p>
          </div>
        )}
      </div>

      {/* Content Gallery — Masonry Wall */}
      <div className="stack">
        <div className="section-header">
          <h2>Content Gallery</h2>
          <span className="text-sm text-muted">
            {contentList ? `${contentList.total} items` : ""}
          </span>
        </div>

        {/* Sort + Platform filters */}
        <div className="gallery-filters">
          <div className="filter-tabs">
            {[
              { label: "Most Recent", value: "newest" },
              { label: "Most Liked", value: "popular" },
            ].map((opt) => (
              <button
                key={opt.value}
                className={`filter-tab ${contentSort === opt.value ? "active" : ""}`}
                onClick={() => handleContentSort(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <div className="platform-tag-list">
            <button
              className={`platform-tag ${contentPlatform === null ? "active" : ""}`}
              onClick={() => handleContentPlatform(null)}
            >
              All
            </button>
            {platforms && [...new Set([
              ...Object.keys(platforms.contents),
            ])].map((p) => (
              <button
                key={p}
                className={`platform-tag ${contentPlatform === p ? "active" : ""}`}
                onClick={() => handleContentPlatform(p)}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {contentLoading && contentPage === 1 ? (
          <div className="masonry-wall">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="masonry-card masonry-card-skeleton">
                <div className="skeleton" style={{ width: "100%", height: 200, borderRadius: 0 }} />
                <div style={{ padding: 12 }}>
                  <div className="skeleton skeleton-text" />
                  <div className="skeleton skeleton-text-sm" style={{ marginTop: 8 }} />
                </div>
              </div>
            ))}
          </div>
        ) : allCards.length > 0 ? (
          <>
            <div className="masonry-wall">
              {allCards.map((card, i) => (
                <ContentMasonryCard key={card.id} card={card} index={i} onClick={() => setSelectedContentId(card.id)} />
              ))}
            </div>
            {contentList?.has_more && (
              <button
                className="btn btn-outline"
                style={{ alignSelf: "center", marginTop: 8 }}
                onClick={() => setContentPage((p) => p + 1)}
                disabled={contentLoading}
              >
                {contentLoading ? "Loading..." : "Load More"}
              </button>
            )}
          </>
        ) : (
          <div className="glass-card" style={{ padding: 32, textAlign: "center" }}>
            <p className="text-sm text-muted">No content yet.</p>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedContentId !== null && (
        <ContentDetailModal contentId={selectedContentId} onClose={closeDetail} />
      )}
    </div>
  )
}
