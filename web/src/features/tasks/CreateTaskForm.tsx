import { useState } from 'react'
import { Send, Search, MessageSquare, User, Check } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { useCreateTaskMutation } from '@/store/api'

type XAction = 'search' | 'tweet' | 'timeline'

const SEARCH_TABS = ['Top', 'Latest', 'Media'] as const
const HAS_FILTERS = [
  { key: 'video', label: 'Video' },
  { key: 'media', label: 'All Media' },
  { key: 'images', label: 'Images' },
  { key: 'links', label: 'Links' },
] as const

export function CreateTaskForm() {
  const [action, setAction] = useState<XAction>('search')
  const [createTask, { isLoading }] = useCreateTaskMutation()
  const [result, setResult] = useState<{ task_id: string } | null>(null)
  const [error, setError] = useState('')

  // Search state
  const [query, setQuery] = useState('')
  const [maxTweets, setMaxTweets] = useState(20)
  const [searchTab, setSearchTab] = useState('Top')
  const [includeRetweets, setIncludeRetweets] = useState(false)
  const [hasFilters, setHasFilters] = useState<string[]>([])

  // Tweet state
  const [tweetUrl, setTweetUrl] = useState('')
  const [maxReplies, setMaxReplies] = useState(20)

  // Timeline state
  const [username, setUsername] = useState('')
  const [tlMaxTweets, setTlMaxTweets] = useState(50)
  const [includeReplies, setIncludeReplies] = useState(false)

  const toggleHasFilter = (key: string) => {
    setHasFilters(prev =>
      prev.includes(key) ? prev.filter(f => f !== key) : [...prev, key],
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setResult(null)

    let payload: Record<string, unknown>

    if (action === 'search') {
      if (!query.trim()) { setError('Search query is required'); return }
      let q = query.trim()
      for (const f of hasFilters) {
        if (!q.includes(`has:${f}`)) q += ` has:${f}`
      }
      payload = { action: 'search', query: q, max_tweets: maxTweets, search_tab: searchTab, include_retweets: includeRetweets }
    } else if (action === 'tweet') {
      if (!tweetUrl.trim()) { setError('Tweet URL or ID is required'); return }
      const input = tweetUrl.trim()
      payload = { action: 'tweet', max_replies: maxReplies, ...(/^\d+$/.test(input) ? { tweet_id: input } : { url: input }) }
    } else {
      if (!username.trim()) { setError('Username is required'); return }
      payload = { action: 'timeline', username: username.trim().replace(/^@/, ''), max_tweets: tlMaxTweets, include_replies: includeReplies }
    }

    try {
      const res = await createTask({ label: 'crawler:x', payload }).unwrap()
      setResult(res)
      if (action === 'search') setQuery('')
      if (action === 'tweet') setTweetUrl('')
      if (action === 'timeline') setUsername('')
    } catch (err) {
      setError(String(err))
    }
  }

  const actions: { key: XAction; icon: React.ReactNode; label: string }[] = [
    { key: 'search', icon: <Search size={15} />, label: 'Search' },
    { key: 'tweet', icon: <MessageSquare size={15} />, label: 'Tweet' },
    { key: 'timeline', icon: <User size={15} />, label: 'Timeline' },
  ]

  return (
    <Card>
      <CardContent>
        {/* Action selector tabs */}
        <div className="flex items-center gap-1 p-1 rounded-lg" style={{ background: 'rgba(100, 116, 139, 0.08)' }}>
          {actions.map(a => (
            <button
              key={a.key}
              type="button"
              onClick={() => { setAction(a.key); setError(''); setResult(null) }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200"
              style={{
                background: action === a.key ? 'white' : 'transparent',
                color: action === a.key ? 'var(--foreground)' : 'var(--foreground-muted)',
                boxShadow: action === a.key ? '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)' : 'none',
                flex: 1,
                justifyContent: 'center',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {a.icon}
              {a.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} style={{ marginTop: '1.25rem' }}>
          {/* Search Form */}
          {action === 'search' && (
            <div className="stack-sm">
              <input
                className="form-input"
                placeholder='Keywords, e.g. "AI robotics" from:elonmusk lang:en'
                value={query}
                onChange={e => setQuery(e.target.value)}
                autoFocus
                style={{ fontSize: '0.9375rem' }}
              />

              {/* Filter chips */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-medium" style={{ color: 'var(--foreground-subtle)' }}>Content:</span>
                {HAS_FILTERS.map(f => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => toggleHasFilter(f.key)}
                    className="px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-150"
                    style={{
                      background: hasFilters.includes(f.key) ? 'var(--teal)' : 'rgba(100, 116, 139, 0.08)',
                      color: hasFilters.includes(f.key) ? 'white' : 'var(--foreground-muted)',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {hasFilters.includes(f.key) && <Check size={10} className="inline mr-1" style={{ verticalAlign: '-1px' }} />}
                    {f.label}
                  </button>
                ))}

                <span className="mx-1" style={{ color: 'var(--foreground-subtle)' }}>|</span>

                <span className="text-xs font-medium" style={{ color: 'var(--foreground-subtle)' }}>Tab:</span>
                {SEARCH_TABS.map(t => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setSearchTab(t)}
                    className="px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-150"
                    style={{
                      background: searchTab === t ? 'var(--teal)' : 'rgba(100, 116, 139, 0.08)',
                      color: searchTab === t ? 'white' : 'var(--foreground-muted)',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {/* Options */}
              <div className="flex items-center gap-5 flex-wrap">
                <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--foreground-muted)' }}>
                  Max
                  <input
                    type="number"
                    className="form-input text-sm"
                    style={{ width: 64, padding: '0.25rem 0.5rem' }}
                    min={1}
                    max={500}
                    value={maxTweets}
                    onChange={e => setMaxTweets(parseInt(e.target.value) || 20)}
                  />
                  tweets
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none" style={{ color: 'var(--foreground-muted)' }}>
                  <input
                    type="checkbox"
                    checked={includeRetweets}
                    onChange={e => setIncludeRetweets(e.target.checked)}
                    className="rounded"
                    style={{ accentColor: 'var(--teal)' }}
                  />
                  Include retweets
                </label>
              </div>
            </div>
          )}

          {/* Tweet Form */}
          {action === 'tweet' && (
            <div className="stack-sm">
              <input
                className="form-input"
                placeholder="https://x.com/user/status/123456... or tweet ID"
                value={tweetUrl}
                onChange={e => setTweetUrl(e.target.value)}
                autoFocus
                style={{ fontSize: '0.9375rem' }}
              />
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--foreground-muted)' }}>
                Max
                <input
                  type="number"
                  className="form-input text-sm"
                  style={{ width: 64, padding: '0.25rem 0.5rem' }}
                  min={0}
                  max={200}
                  value={maxReplies}
                  onChange={e => setMaxReplies(parseInt(e.target.value) || 20)}
                />
                replies
              </label>
            </div>
          )}

          {/* Timeline Form */}
          {action === 'timeline' && (
            <div className="stack-sm">
              <div className="relative">
                <span
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-medium"
                  style={{ color: 'var(--foreground-subtle)' }}
                >
                  @
                </span>
                <input
                  className="form-input"
                  style={{ paddingLeft: '1.75rem', fontSize: '0.9375rem' }}
                  placeholder="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="flex items-center gap-5 flex-wrap">
                <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--foreground-muted)' }}>
                  Max
                  <input
                    type="number"
                    className="form-input text-sm"
                    style={{ width: 64, padding: '0.25rem 0.5rem' }}
                    min={1}
                    max={500}
                    value={tlMaxTweets}
                    onChange={e => setTlMaxTweets(parseInt(e.target.value) || 50)}
                  />
                  tweets
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none" style={{ color: 'var(--foreground-muted)' }}>
                  <input
                    type="checkbox"
                    checked={includeReplies}
                    onChange={e => setIncludeReplies(e.target.checked)}
                    className="rounded"
                    style={{ accentColor: 'var(--teal)' }}
                  />
                  Include replies
                </label>
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="flex items-center gap-3" style={{ marginTop: '1rem' }}>
            <Button type="submit" disabled={isLoading}>
              <Send size={14} />
              {isLoading ? 'Submitting...' : 'Submit'}
            </Button>
            {result && (
              <span className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--success)' }}>
                <Check size={14} />
                Task {result.task_id.slice(0, 8)}... created
              </span>
            )}
            {error && (
              <span className="text-sm" style={{ color: 'var(--error)' }}>{error}</span>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
