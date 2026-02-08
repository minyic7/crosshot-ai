import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Heart, MessageCircle, Repeat2, Quote, Eye, Film } from 'lucide-react'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { useGetContentQuery } from '@/store/api'

interface TweetData {
  tweet_id: string
  text: string
  created_at: string
  lang: string
  source_url: string
  is_retweet: boolean
  is_reply: boolean
  is_quote: boolean
  author: {
    user_id: string
    username: string
    display_name: string
    verified: boolean
    followers_count: number
  }
  metrics: {
    reply_count: number
    retweet_count: number
    like_count: number
    quote_count: number
    views_count: number
  }
  media: Array<{ type: string; url: string; video_url?: string; local_path?: string; video_local_path?: string }>
  urls: string[]
  hashtags: string[]
  quoted_tweet: TweetData | null
  reply_to: { tweet_id: string; username: string } | null
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

function MediaGrid({ media }: { media: TweetData['media'] }) {
  if (media.length === 0) return null

  const photos = media.filter(m => m.type === 'photo')
  const videos = media.filter(m => m.type === 'video' || m.type === 'animated_gif')

  return (
    <div className="stack-sm">
      {/* Video players */}
      {videos.map((v, i) => {
        const hasLocalVideo = !!v.video_local_path
        return (
          <div
            key={`video-${i}`}
            style={{
              borderRadius: 12,
              overflow: 'hidden',
              background: '#000',
            }}
          >
            {hasLocalVideo ? (
              <video
                src={mediaUrl(v.video_local_path)}
                controls={v.type === 'video'}
                autoPlay={v.type === 'animated_gif'}
                loop={v.type === 'animated_gif'}
                muted={v.type === 'animated_gif'}
                playsInline
                poster={mediaUrl(v.local_path, v.url)}
                style={{ width: '100%', maxHeight: 480, display: 'block' }}
              />
            ) : (
              /* No local file — show thumbnail with link to original */
              <a
                href={v.video_url ?? v.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'block', position: 'relative' }}
              >
                <img
                  src={v.url}
                  alt="Video thumbnail"
                  style={{ width: '100%', maxHeight: 480, objectFit: 'contain', display: 'block' }}
                />
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'rgba(0,0,0,0.35)',
                  }}
                >
                  <div
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: '50%',
                      background: 'rgba(255,255,255,0.9)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="#000"><path d="M8 5v14l11-7z"/></svg>
                  </div>
                </div>
              </a>
            )}
            <div
              style={{
                padding: '6px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                background: 'rgba(0,0,0,0.85)',
              }}
            >
              <Film size={12} style={{ color: '#94a3b8' }} />
              <span style={{ fontSize: '0.6875rem', color: '#94a3b8', fontWeight: 500 }}>
                {v.type === 'animated_gif' ? 'GIF' : 'Video'}
                {!hasLocalVideo && ' (not downloaded)'}
              </span>
              {v.video_url && (
                <a
                  href={v.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto flex items-center gap-1"
                  style={{ fontSize: '0.6875rem', color: '#64748b', textDecoration: 'none' }}
                >
                  <ExternalLink size={10} /> Open on X
                </a>
              )}
            </div>
          </div>
        )
      })}

      {/* Photo grid */}
      {photos.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: photos.length === 1 ? '1fr' : 'repeat(2, 1fr)',
            gap: 4,
            borderRadius: 12,
            overflow: 'hidden',
          }}
        >
          {photos.map((p, i) => (
            <a
              key={`photo-${i}`}
              href={mediaUrl(p.local_path, p.url)}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'block',
                lineHeight: 0,
                ...(photos.length === 3 && i === 0 ? { gridRow: 'span 2' } : {}),
              }}
            >
              <img
                src={mediaUrl(p.local_path, p.url)}
                alt={`Photo ${i + 1}`}
                style={{
                  width: '100%',
                  height: photos.length === 1 ? 'auto' : '100%',
                  maxHeight: photos.length === 1 ? 500 : 240,
                  objectFit: 'cover',
                  display: 'block',
                }}
              />
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function TweetCard({ tweet, nested = false }: { tweet: TweetData; nested?: boolean }) {
  return (
    <Card
      className={nested ? 'mt-3' : ''}
      style={nested ? { opacity: 0.85, borderLeft: '3px solid var(--teal)' } : undefined}
    >
      <CardContent>
        {/* Author */}
        <div className="flex items-center gap-3 mb-3">
          <div
            style={{
              width: nested ? 32 : 40,
              height: nested ? 32 : 40,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--teal), #434e61)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontSize: nested ? '0.75rem' : '0.875rem',
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            {tweet.author.display_name.charAt(0).toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="flex items-center gap-1.5">
              <span
                className="font-semibold truncate"
                style={{ fontSize: nested ? '0.875rem' : '0.9375rem' }}
              >
                {tweet.author.display_name}
              </span>
              {tweet.author.verified && (
                <Badge variant="success" style={{ fontSize: '0.625rem', padding: '1px 6px' }}>
                  Verified
                </Badge>
              )}
            </div>
            <span className="text-xs" style={{ color: 'var(--foreground-muted)' }}>
              @{tweet.author.username}
            </span>
          </div>
          <span
            className="text-xs"
            style={{ color: 'var(--foreground-subtle)', whiteSpace: 'nowrap' }}
          >
            {formatNumber(tweet.author.followers_count)} followers
          </span>
        </div>

        {/* Reply context */}
        {tweet.reply_to && (
          <p className="text-xs mb-2" style={{ color: 'var(--foreground-muted)' }}>
            Replying to{' '}
            <span style={{ color: 'var(--teal)', fontWeight: 500 }}>
              @{tweet.reply_to.username}
            </span>
          </p>
        )}

        {/* Tweet text */}
        <p
          className="mb-3 whitespace-pre-wrap"
          style={{ lineHeight: 1.7, fontSize: nested ? '0.875rem' : '0.9375rem' }}
        >
          {tweet.text}
        </p>

        {/* Hashtags */}
        {tweet.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {tweet.hashtags.map((tag) => (
              <Badge key={tag} variant="muted">
                #{tag}
              </Badge>
            ))}
          </div>
        )}

        {/* Media */}
        {tweet.media.length > 0 && (
          <div className="mb-3">
            <MediaGrid media={tweet.media} />
          </div>
        )}

        {/* URLs */}
        {tweet.urls.length > 0 && (
          <div className="mb-3">
            {tweet.urls.map((url, i) => (
              <a
                key={i}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs block truncate underline"
                style={{ color: 'var(--teal)' }}
              >
                {url}
              </a>
            ))}
          </div>
        )}

        {/* Metrics bar */}
        <div
          className="flex items-center gap-4 flex-wrap"
          style={{
            padding: '10px 14px',
            borderRadius: 10,
            background: 'rgba(100, 116, 139, 0.05)',
            border: '1px solid rgba(100, 116, 139, 0.1)',
          }}
        >
          {[
            { icon: <MessageCircle size={14} />, value: tweet.metrics.reply_count, label: 'Replies' },
            { icon: <Repeat2 size={14} />, value: tweet.metrics.retweet_count, label: 'Retweets' },
            { icon: <Heart size={14} />, value: tweet.metrics.like_count, label: 'Likes' },
            { icon: <Quote size={14} />, value: tweet.metrics.quote_count, label: 'Quotes' },
            { icon: <Eye size={14} />, value: tweet.metrics.views_count, label: 'Views' },
          ].map((m, i) => (
            <span
              key={i}
              className="flex items-center gap-1.5 text-xs"
              style={{ color: 'var(--foreground-muted)' }}
              title={m.label}
            >
              {m.icon}
              <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {formatNumber(m.value)}
              </span>
            </span>
          ))}
        </div>

        {/* Quoted tweet */}
        {tweet.quoted_tweet && (
          <div className="mt-3">
            <TweetCard tweet={tweet.quoted_tweet} nested />
          </div>
        )}

        {/* Footer */}
        <div
          className="flex items-center gap-3 mt-3 pt-2 flex-wrap"
          style={{ borderTop: '1px solid rgba(100, 116, 139, 0.12)', color: 'var(--foreground-subtle)' }}
        >
          <span className="text-xs">{tweet.created_at}</span>
          <span className="text-xs">lang: {tweet.lang}</span>
          {tweet.is_retweet && <Badge variant="muted">Retweet</Badge>}
          {tweet.is_reply && <Badge variant="muted">Reply</Badge>}
          {tweet.is_quote && <Badge variant="muted">Quote</Badge>}
          <a
            href={tweet.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1 text-xs"
            style={{ color: 'var(--teal)' }}
          >
            <ExternalLink size={12} /> View on X
          </a>
        </div>
      </CardContent>
    </Card>
  )
}

export function ContentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: content, isLoading, isError } = useGetContentQuery(id ?? '', { skip: !id })

  if (isLoading) {
    return (
      <div className="stack">
        <Skeleton className="w-48 h-8" />
        <Skeleton className="w-full h-64" />
      </div>
    )
  }

  if (isError || !content || ('error' in content)) {
    return (
      <div className="stack">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <p style={{ color: 'var(--error)' }}>Content not found</p>
      </div>
    )
  }

  const tweet = content.data as unknown as TweetData

  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <h1 className="text-xl font-semibold">Content Detail</h1>
      </div>

      {/* Metadata */}
      <Card>
        <CardContent>
          <CardHeader className="mb-3">
            <CardDescription>Metadata</CardDescription>
          </CardHeader>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span style={{ color: 'var(--foreground-muted)' }}>Content ID:</span>{' '}
              <code className="text-xs">{content.id}</code>
            </div>
            <div>
              <span style={{ color: 'var(--foreground-muted)' }}>Task ID:</span>{' '}
              <code className="text-xs">{content.task_id}</code>
            </div>
            <div>
              <span style={{ color: 'var(--foreground-muted)' }}>Platform:</span>{' '}
              <Badge variant="muted">{content.platform}</Badge>
            </div>
            <div>
              <span style={{ color: 'var(--foreground-muted)' }}>Crawled:</span>{' '}
              {new Date(content.crawled_at).toLocaleString()}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tweet content */}
      {content.platform === 'x' && tweet?.tweet_id ? (
        <TweetCard tweet={tweet} />
      ) : (
        <Card>
          <CardContent>
            <CardHeader className="mb-3">
              <CardDescription>Raw Data</CardDescription>
            </CardHeader>
            <pre
              className="text-xs overflow-auto p-3"
              style={{ background: 'var(--background)', borderRadius: 8, maxHeight: 500 }}
            >
              {JSON.stringify(content.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
