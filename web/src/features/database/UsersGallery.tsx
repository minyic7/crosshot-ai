import { useNavigate } from 'react-router-dom'
import { Clock, BarChart3, ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListUsersQuery } from '@/store/api'

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

export function UsersGallery() {
  const navigate = useNavigate()
  const { data: users, isLoading } = useListUsersQuery()

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
    <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
      {users.map((user, i) => {
        const badge = STATUS_BADGE[user.status] ?? STATUS_BADGE.pending
        const summary = user.last_summary ? stripMarkdown(user.last_summary) : null

        return (
          <div
            key={user.id}
            className="db-user-card rise"
            style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
            onClick={() => navigate(`/user/${user.id}`)}
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
        )
      })}
    </div>
  )
}
