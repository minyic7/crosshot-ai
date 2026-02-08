import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Heart, MessageCircle, Repeat2, Quote, Eye } from 'lucide-react'
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
  media: Array<{ type: string; url: string; video_url?: string }>
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

function TweetCard({ tweet, nested = false }: { tweet: TweetData; nested?: boolean }) {
  return (
    <Card className={nested ? 'mt-3' : ''} style={nested ? { opacity: 0.85, borderLeft: '3px solid var(--accent)' } : undefined}>
      <CardContent>
        {/* Author */}
        <div className="flex items-center gap-2 mb-3">
          <div>
            <span className="font-semibold">{tweet.author.display_name}</span>
            {tweet.author.verified && <Badge variant="success" className="ml-1">Verified</Badge>}
            <span className="text-sm ml-2" style={{ color: 'var(--foreground-muted)' }}>
              @{tweet.author.username}
            </span>
          </div>
          <span className="text-xs ml-auto" style={{ color: 'var(--foreground-subtle)' }}>
            {formatNumber(tweet.author.followers_count)} followers
          </span>
        </div>

        {/* Reply context */}
        {tweet.reply_to && (
          <p className="text-xs mb-2" style={{ color: 'var(--foreground-muted)' }}>
            Replying to @{tweet.reply_to.username}
          </p>
        )}

        {/* Tweet text */}
        <p className="mb-3 whitespace-pre-wrap" style={{ lineHeight: 1.6 }}>{tweet.text}</p>

        {/* Hashtags */}
        {tweet.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {tweet.hashtags.map((tag) => (
              <Badge key={tag} variant="muted">#{tag}</Badge>
            ))}
          </div>
        )}

        {/* Media */}
        {tweet.media.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {tweet.media.map((m, i) => (
              <div key={i} className="text-sm">
                {m.type === 'photo' ? (
                  <a href={m.url} target="_blank" rel="noopener noreferrer">
                    <img
                      src={m.url}
                      alt={`Media ${i + 1}`}
                      style={{ maxWidth: 300, maxHeight: 200, borderRadius: 8, objectFit: 'cover' }}
                    />
                  </a>
                ) : (
                  <div className="flex items-center gap-1">
                    <Badge variant="warning">{m.type}</Badge>
                    <a
                      href={m.video_url ?? m.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs underline"
                      style={{ color: 'var(--accent)' }}
                    >
                      Open {m.type}
                    </a>
                  </div>
                )}
              </div>
            ))}
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
                style={{ color: 'var(--accent)' }}
              >
                {url}
              </a>
            ))}
          </div>
        )}

        {/* Metrics */}
        <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--foreground-muted)' }}>
          <span className="flex items-center gap-1"><MessageCircle size={14} /> {formatNumber(tweet.metrics.reply_count)}</span>
          <span className="flex items-center gap-1"><Repeat2 size={14} /> {formatNumber(tweet.metrics.retweet_count)}</span>
          <span className="flex items-center gap-1"><Heart size={14} /> {formatNumber(tweet.metrics.like_count)}</span>
          <span className="flex items-center gap-1"><Quote size={14} /> {formatNumber(tweet.metrics.quote_count)}</span>
          <span className="flex items-center gap-1"><Eye size={14} /> {formatNumber(tweet.metrics.views_count)}</span>
        </div>

        {/* Quoted tweet */}
        {tweet.quoted_tweet && (
          <div className="mt-3 pl-2">
            <p className="text-xs mb-1" style={{ color: 'var(--foreground-muted)' }}>Quoted tweet:</p>
            <TweetCard tweet={tweet.quoted_tweet} nested />
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-3 mt-3 pt-2" style={{ borderTop: '1px solid var(--border)', color: 'var(--foreground-subtle)' }}>
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
            style={{ color: 'var(--accent)' }}
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
            <div><span style={{ color: 'var(--foreground-muted)' }}>Content ID:</span> <code className="text-xs">{content.id}</code></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Task ID:</span> <code className="text-xs">{content.task_id}</code></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Platform:</span> <Badge variant="muted">{content.platform}</Badge></div>
            <div><span style={{ color: 'var(--foreground-muted)' }}>Crawled:</span> {new Date(content.crawled_at).toLocaleString()}</div>
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
            <pre className="text-xs overflow-auto p-3" style={{ background: 'var(--background)', borderRadius: 8, maxHeight: 500 }}>
              {JSON.stringify(content.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
