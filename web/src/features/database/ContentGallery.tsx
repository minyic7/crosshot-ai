import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Heart, MessageCircle, Repeat2, Eye, Film, Image as ImageIcon, Play } from 'lucide-react'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListContentsQuery } from '@/store/api'

const PAGE_SIZE = 20
const COLUMN_WIDTH = 280
const GAP = 16

interface TweetData {
  tweet_id?: string
  text?: string
  author?: {
    username?: string
    display_name?: string
    verified?: boolean
  }
  metrics?: {
    reply_count?: number
    retweet_count?: number
    like_count?: number
    views_count?: number
  }
  media?: Array<{
    type: string
    url: string
    video_url?: string
    local_path?: string
    video_local_path?: string
    width?: number
    height?: number
  }>
  hashtags?: string[]
  created_at?: string
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

/** Convert a NAS local path like /data/media/x/... to a /media/x/... URL */
function mediaUrl(localPath?: string, fallback?: string): string {
  if (localPath) return localPath.replace(/^\/data\/media/, '/media')
  return fallback ?? ''
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d`
  return `${Math.floor(days / 30)}mo`
}

export function ContentGallery() {
  const navigate = useNavigate()
  const [platform, setPlatform] = useState('')
  const [offset, setOffset] = useState(0)
  const [allContents, setAllContents] = useState<Array<{ id: string; platform: string; crawled_at: string; data: Record<string, unknown> }>>([])
  const [hasMore, setHasMore] = useState(true)
  const loadingRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isFetching } = useListContentsQuery(
    { platform: platform || undefined, limit: PAGE_SIZE, offset } as { platform?: string; limit: number; offset: number },
    { refetchOnMountOrArgChange: true },
  )

  // Reset on platform change
  useEffect(() => {
    setAllContents([])
    setOffset(0)
    setHasMore(true)
  }, [platform])

  // Append new data
  useEffect(() => {
    if (!data) return
    const newItems = data.contents ?? []
    if (offset === 0) {
      setAllContents(newItems)
    } else {
      setAllContents(prev => {
        const existingIds = new Set(prev.map(c => c.id))
        const unique = newItems.filter((c: { id: string }) => !existingIds.has(c.id))
        return [...prev, ...unique]
      })
    }
    setHasMore(newItems.length >= PAGE_SIZE)
    loadingRef.current = false
  }, [data, offset])

  // Infinite scroll observer
  const observerCallback = useCallback((entries: IntersectionObserverEntry[]) => {
    if (entries[0]?.isIntersecting && hasMore && !isFetching && !loadingRef.current) {
      loadingRef.current = true
      setOffset(prev => prev + PAGE_SIZE)
    }
  }, [hasMore, isFetching])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(observerCallback, { rootMargin: '400px' })
    observer.observe(el)
    return () => observer.disconnect()
  }, [observerCallback])

  // Masonry layout calculation
  const [columns, setColumns] = useState(4)
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const update = () => {
      const w = container.clientWidth
      setColumns(Math.max(1, Math.floor((w + GAP) / (COLUMN_WIDTH + GAP))))
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // Distribute items into columns (shortest-column-first)
  const columnItems: Array<typeof allContents> = Array.from({ length: columns }, () => [])
  const columnHeights = new Array(columns).fill(0)

  for (const content of allContents) {
    const tweet = content.data as unknown as TweetData
    const hasMedia = (tweet?.media?.length ?? 0) > 0
    const estimatedHeight = hasMedia ? 340 : 200
    const shortestCol = columnHeights.indexOf(Math.min(...columnHeights))
    columnItems[shortestCol].push(content)
    columnHeights[shortestCol] += estimatedHeight + GAP
  }

  const platforms = ['', 'x', 'xhs']

  return (
    <div className="stack">
      {/* Platform filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold tracking-wide" style={{ color: 'var(--foreground-subtle)', textTransform: 'uppercase' }}>
          Platform
        </span>
        <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: 'rgba(100, 116, 139, 0.08)' }}>
          {platforms.map(p => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className="px-3 py-1 rounded-md text-xs font-medium transition-all"
              style={{
                background: platform === p ? 'white' : 'transparent',
                color: platform === p ? 'var(--foreground)' : 'var(--foreground-muted)',
                boxShadow: platform === p ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {p ? p.toUpperCase() : 'All'}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-xs ml-2" style={{ color: 'var(--foreground-subtle)' }}>
            {data.total} items
          </span>
        )}
      </div>

      {/* Masonry grid */}
      <div ref={containerRef} className="w-full">
        {isLoading && allContents.length === 0 ? (
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className={`rounded-xl ${i % 2 === 0 ? 'h-52' : 'h-72'}`} />
            ))}
          </div>
        ) : allContents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16">
            <ImageIcon size={40} style={{ color: 'var(--foreground-subtle)', opacity: 0.4 }} />
            <p className="text-sm mt-3" style={{ color: 'var(--foreground-subtle)' }}>No content yet</p>
          </div>
        ) : (
          <div className="flex" style={{ gap: GAP }}>
            {columnItems.map((col, colIdx) => (
              <div key={colIdx} className="flex flex-col" style={{ flex: 1, gap: GAP, minWidth: 0 }}>
                {col.map(content => (
                  <MasonryCard
                    key={content.id}
                    content={content}
                    onClick={() => navigate(`/content/${content.id}`)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sentinel for infinite scroll */}
      <div ref={sentinelRef} style={{ height: 1 }} />
      {isFetching && allContents.length > 0 && (
        <div className="flex justify-center py-4">
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--foreground-muted)' }}>
            <div className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
            Loading more...
          </div>
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────
// Masonry Card
// ──────────────────────────────────────────────

function MasonryCard({
  content,
  onClick,
}: {
  content: { id: string; platform: string; crawled_at: string; data: Record<string, unknown> }
  onClick: () => void
}) {
  const tweet = content.data as unknown as TweetData
  const media = tweet?.media ?? []
  const firstMedia = media[0]
  const hasImage = firstMedia?.type === 'photo' && firstMedia?.url
  const hasVideo = firstMedia?.type === 'video'
  const metrics = tweet?.metrics
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)

  return (
    <div
      onClick={onClick}
      className="group rounded-xl overflow-hidden transition-all duration-300 cursor-pointer"
      style={{
        background: 'rgba(255, 255, 255, 0.85)',
        border: '1px solid rgba(100, 116, 139, 0.15)',
        boxShadow: '0 1px 4px rgba(100, 116, 139, 0.06)',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'translateY(-3px)'
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(100, 116, 139, 0.14), 0 2px 8px rgba(0,0,0,0.04)'
        e.currentTarget.style.borderColor = 'rgba(100, 116, 139, 0.25)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = '0 1px 4px rgba(100, 116, 139, 0.06)'
        e.currentTarget.style.borderColor = 'rgba(100, 116, 139, 0.15)'
      }}
    >
      {/* Media */}
      {(hasImage || hasVideo) && !imgError && (
        <div className="relative overflow-hidden" style={{ background: 'rgba(100,116,139,0.05)' }}>
          {!imgLoaded && (
            <div className="skeleton" style={{ width: '100%', height: 180 }} />
          )}
          <img
            src={mediaUrl(firstMedia!.local_path, firstMedia!.url)}
            alt=""
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
            style={{
              width: '100%',
              display: imgLoaded ? 'block' : 'none',
            }}
            loading="lazy"
          />
          {/* Video overlay badge */}
          {hasVideo && (
            <div
              className="absolute bottom-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold"
              style={{
                background: 'rgba(0,0,0,0.65)',
                color: 'white',
                backdropFilter: 'blur(4px)',
              }}
            >
              <Play size={10} fill="white" />
              Video
            </div>
          )}
          {/* Media count badge */}
          {media.length > 1 && (
            <div
              className="absolute top-2 right-2 flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold"
              style={{
                background: 'rgba(0,0,0,0.55)',
                color: 'white',
                backdropFilter: 'blur(4px)',
              }}
            >
              {media.filter(m => m.type === 'video').length > 0 ? <Film size={10} /> : <ImageIcon size={10} />}
              {media.length}
            </div>
          )}
        </div>
      )}

      {/* Content body */}
      <div className="px-3 py-2.5">
        {/* Author row */}
        {tweet?.author && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-xs font-semibold truncate" style={{ color: 'var(--foreground)', maxWidth: '60%' }}>
              {tweet.author.display_name}
            </span>
            <span className="text-xs truncate" style={{ color: 'var(--foreground-subtle)' }}>
              @{tweet.author.username}
            </span>
            {tweet.author.verified && (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="var(--blue)"><path d="M22.5 12.5c0-1.58-.875-2.95-2.148-3.6.154-.435.238-.905.238-1.4 0-2.21-1.71-3.998-3.818-3.998-.47 0-.92.084-1.336.25C14.818 2.415 13.51 1.5 12 1.5s-2.816.917-3.437 2.25c-.415-.165-.866-.25-1.336-.25-2.11 0-3.818 1.79-3.818 4 0 .494.083.964.237 1.4-1.272.65-2.147 2.018-2.147 3.6 0 1.495.782 2.798 1.942 3.486-.02.17-.032.34-.032.514 0 2.21 1.708 4 3.818 4 .47 0 .92-.086 1.335-.25.62 1.334 1.926 2.25 3.437 2.25 1.512 0 2.818-.916 3.437-2.25.415.163.865.248 1.336.248 2.11 0 3.818-1.79 3.818-4 0-.174-.012-.344-.033-.513 1.158-.687 1.943-1.99 1.943-3.484zm-6.616-3.334l-4.334 6.5c-.145.217-.382.334-.625.334-.143 0-.288-.04-.416-.126l-.115-.094-2.415-2.415c-.293-.293-.293-.768 0-1.06s.768-.294 1.06 0l1.77 1.767 3.825-5.74c.23-.345.696-.436 1.04-.207.346.23.44.696.21 1.04z"/></svg>
            )}
          </div>
        )}

        {/* Text */}
        {tweet?.text && (
          <p
            className="text-xs leading-relaxed mb-2"
            style={{
              color: 'var(--foreground-muted)',
              display: '-webkit-box',
              WebkitLineClamp: hasImage || hasVideo ? 3 : 6,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {tweet.text}
          </p>
        )}

        {/* Hashtags */}
        {tweet?.hashtags && tweet.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {tweet.hashtags.slice(0, 3).map(tag => (
              <span key={tag} className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(90,138,184,0.1)', color: 'var(--blue)', fontSize: '0.625rem' }}>
                #{tag}
              </span>
            ))}
            {tweet.hashtags.length > 3 && (
              <span className="text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>+{tweet.hashtags.length - 3}</span>
            )}
          </div>
        )}

        {/* Metrics + time footer */}
        <div className="flex items-center justify-between pt-1.5" style={{ borderTop: '1px solid rgba(100,116,139,0.08)' }}>
          <div className="flex items-center gap-2.5">
            {metrics && (
              <>
                <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>
                  <Heart size={10} /> {formatNumber(metrics.like_count ?? 0)}
                </span>
                <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>
                  <Repeat2 size={10} /> {formatNumber(metrics.retweet_count ?? 0)}
                </span>
                <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>
                  <MessageCircle size={10} /> {formatNumber(metrics.reply_count ?? 0)}
                </span>
                {metrics.views_count ? (
                  <span className="flex items-center gap-0.5 text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>
                    <Eye size={10} /> {formatNumber(metrics.views_count)}
                  </span>
                ) : null}
              </>
            )}
          </div>
          <span className="text-xs" style={{ color: 'var(--foreground-subtle)', fontSize: '0.625rem' }}>
            {timeAgo(content.crawled_at)}
          </span>
        </div>
      </div>
    </div>
  )
}
