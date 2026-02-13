import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, BarChart3, ExternalLink, ChevronDown, Heart, Repeat2, MessageCircle, Eye, Film, Image as ImageIcon, Play } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListUsersQuery, useListContentsQuery } from '@/store/api'

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return `${Math.floor(days / 30)}mo ago`
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function mediaUrl(localPath?: string, fallback?: string): string {
  if (localPath) return localPath.replace(/^\/data\/media/, '/media')
  return fallback ?? ''
}

function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s/g, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/[_*~`>]/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim()
}

const STATUS_BADGE: Record<string, { variant: 'success' | 'warning' | 'muted'; label: string }> = {
  active: { variant: 'success', label: 'Active' },
  paused: { variant: 'warning', label: 'Paused' },
  pending: { variant: 'muted', label: 'Pending' },
}

interface TweetData {
  tweet_id?: string
  text?: string
  author?: { username?: string; display_name?: string }
  metrics?: { reply_count?: number; retweet_count?: number; like_count?: number; views_count?: number }
  media?: Array<{ type: string; url: string; local_path?: string }>
  created_at?: string
}

export function UsersGallery() {
  const navigate = useNavigate()
  const { data: users, isLoading } = useListUsersQuery()
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="rounded-xl h-48" />
        ))}
      </div>
    )
  }

  if (!users || users.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <span style={{ fontSize: 40, opacity: 0.4 }}>👤</span>
        <p className="text-sm mt-3" style={{ color: 'var(--foreground-subtle)' }}>No users yet</p>
      </div>
    )
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      {users.map((user, i) => {
        const badge = STATUS_BADGE[user.status] ?? STATUS_BADGE.pending
        const summary = user.last_summary ? stripMarkdown(user.last_summary) : null
        const isExpanded = expandedUserId === user.id

        return (
          <div key={user.id}>
            <div
              className={`db-user-card rise ${isExpanded ? 'expanded' : ''}`}
              style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
              onClick={() => setExpandedUserId(isExpanded ? null : user.id)}
            >
              <div className="db-user-card-shimmer" />

              {/* Header */}
              <div className="db-user-card-header">
                <div className="db-user-card-avatar">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="flex items-center gap-1.5">
                    <span className="db-user-card-name truncate">{user.name}</span>
                    <Badge variant={badge.variant} style={{ fontSize: '0.625rem', padding: '1px 6px' }}>
                      {badge.label}
                    </Badge>
                  </div>
                  {user.username && (
                    <span className="db-user-card-handle">@{user.username}</span>
                  )}
                </div>
                <Badge variant="muted" style={{ fontSize: '0.625rem', flexShrink: 0 }}>
                  {user.platform.toUpperCase()}
                </Badge>
                <ChevronDown
                  size={14}
                  style={{
                    color: 'var(--ink-3)',
                    transition: 'transform 0.2s ease',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)',
                    flexShrink: 0,
                  }}
                />
              </div>

              {/* Summary snippet */}
              <div className="db-user-card-body">
                {summary ? (
                  <p className="db-user-card-summary">{summary}</p>
                ) : (
                  <p className="db-user-card-empty">Awaiting first analysis...</p>
                )}
              </div>

              {/* Footer */}
              <div className="db-user-card-footer">
                <div className="db-user-card-stats">
                  <span className="db-user-card-stat">
                    <BarChart3 size={11} />
                    {user.total_contents} posts
                  </span>
                  {user.last_crawl_at && (
                    <span className="db-user-card-stat">
                      <Clock size={11} />
                      {timeAgo(user.last_crawl_at)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {user.profile_url && (
                    <a
                      href={user.profile_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="db-user-card-link"
                      onClick={e => e.stopPropagation()}
                    >
                      <ExternalLink size={11} />
                    </a>
                  )}
                  <button
                    className="db-user-card-link"
                    style={{ fontSize: '0.6875rem', fontWeight: 500, width: 'auto', padding: '0 6px' }}
                    onClick={e => { e.stopPropagation(); navigate(`/user/${user.id}`) }}
                  >
                    Detail
                  </button>
                </div>
              </div>

              {/* Topic tags */}
              {user.topics && user.topics.length > 0 && (
                <div className="db-user-card-topics">
                  {user.topics.slice(0, 3).map(t => (
                    <span key={t.id} className="db-user-card-topic">{t.icon} {t.name}</span>
                  ))}
                  {user.topics.length > 3 && (
                    <span className="db-user-card-topic-more">+{user.topics.length - 3}</span>
                  )}
                </div>
              )}
            </div>

            {/* Expanded content list */}
            {isExpanded && (
              <UserContentsList userId={user.id} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ──────────────────────────────────────────────
// Inline content list for expanded user card
// ──────────────────────────────────────────────

function UserContentsList({ userId }: { userId: string }) {
  const navigate = useNavigate()
  const { data, isLoading } = useListContentsQuery({ user_id: userId, limit: 50 })

  if (isLoading) {
    return (
      <div className="db-user-contents">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="rounded-lg h-20" />
        ))}
      </div>
    )
  }

  const contents = data?.contents ?? []

  if (contents.length === 0) {
    return (
      <div className="db-user-contents">
        <p className="text-xs" style={{ color: 'var(--ink-4)', textAlign: 'center', padding: 16 }}>
          No content crawled yet
        </p>
      </div>
    )
  }

  return (
    <div className="db-user-contents">
      {contents.map(content => {
        const tweet = content.data as unknown as TweetData
        const media = tweet?.media ?? []
        const firstMedia = media[0]
        const hasThumb = firstMedia && (firstMedia.local_path || firstMedia.url)
        const isVideo = firstMedia?.type === 'video' || firstMedia?.type === 'animated_gif'
        const metrics = tweet?.metrics

        return (
          <div
            key={content.id}
            className="db-user-content-row"
            onClick={() => navigate(`/content/${content.id}`)}
          >
            {/* Thumbnail */}
            {hasThumb && (
              <div className="db-user-content-thumb">
                <img
                  src={mediaUrl(firstMedia!.local_path, firstMedia!.url)}
                  alt=""
                />
                {isVideo && (
                  <div className="db-user-content-thumb-badge">
                    <Play size={8} fill="white" />
                  </div>
                )}
                {media.length > 1 && (
                  <div className="db-user-content-thumb-badge" style={{ top: 2, right: 2, bottom: 'auto', left: 'auto' }}>
                    {media.filter(m => m.type === 'video').length > 0 ? <Film size={8} /> : <ImageIcon size={8} />}
                    {media.length}
                  </div>
                )}
              </div>
            )}

            {/* Text + metrics */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {tweet?.text && (
                <p className="db-user-content-text">{tweet.text}</p>
              )}
              <div className="db-user-content-meta">
                {metrics && (
                  <>
                    <span><Heart size={10} /> {formatNumber(metrics.like_count ?? 0)}</span>
                    <span><Repeat2 size={10} /> {formatNumber(metrics.retweet_count ?? 0)}</span>
                    <span><MessageCircle size={10} /> {formatNumber(metrics.reply_count ?? 0)}</span>
                    {metrics.views_count ? <span><Eye size={10} /> {formatNumber(metrics.views_count)}</span> : null}
                  </>
                )}
                <span className="db-user-content-time">
                  {tweet?.created_at ? timeAgo(tweet.created_at) : timeAgo(content.crawled_at)}
                </span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
