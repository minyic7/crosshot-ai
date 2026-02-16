import { useState } from 'react'
import { Send, Search, MessageSquare, User, Check } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { useCreateTaskMutation } from '@/store/api'

type XAction = 'search' | 'tweet' | 'timeline'

const SEARCH_TABS = ['Top', 'Latest', 'Media'] as const
const HAS_FILTERS = [
  { key: 'video', label: 'Video' },
  { key: 'media', label: 'All Media' },
  { key: 'images', label: 'Images' },
  { key: 'links', label: 'Links' },
] as const

interface SubmitTaskModalProps {
  open: boolean
  onClose: () => void
}

export function SubmitTaskModal({ open, onClose }: SubmitTaskModalProps) {
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
      // Reset fields
      if (action === 'search') setQuery('')
      if (action === 'tweet') setTweetUrl('')
      if (action === 'timeline') setUsername('')
      // Auto-close after brief success
      setTimeout(() => { onClose(); setResult(null) }, 800)
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
    <Modal open={open} onClose={onClose} title="Submit Task" className="submit-modal">
      {/* Action selector tabs */}
      <div className="submit-modal-tabs">
        {actions.map(a => (
          <button
            key={a.key}
            type="button"
            onClick={() => { setAction(a.key); setError(''); setResult(null) }}
            className={`submit-modal-tab${action === a.key ? ' active' : ''}`}
          >
            {a.icon}
            {a.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="submit-modal-form">
        {/* Search Form */}
        {action === 'search' && (
          <div className="submit-modal-fields">
            <input
              className="submit-modal-input"
              placeholder='Keywords, e.g. "AI robotics" from:elonmusk lang:en'
              value={query}
              onChange={e => setQuery(e.target.value)}
              autoFocus
            />
            <div className="submit-modal-filter-row">
              <span className="submit-modal-filter-label">Content:</span>
              {HAS_FILTERS.map(f => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => toggleHasFilter(f.key)}
                  className={`submit-modal-pill${hasFilters.includes(f.key) ? ' active' : ''}`}
                >
                  {hasFilters.includes(f.key) && <Check size={10} className="inline mr-1" style={{ verticalAlign: '-1px' }} />}
                  {f.label}
                </button>
              ))}
              <span className="submit-modal-separator">|</span>
              <span className="submit-modal-filter-label">Tab:</span>
              {SEARCH_TABS.map(t => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setSearchTab(t)}
                  className={`submit-modal-pill${searchTab === t ? ' active' : ''}`}
                >
                  {t}
                </button>
              ))}
            </div>
            <div className="submit-modal-options">
              <label className="submit-modal-option-label">
                Max
                <input type="number" className="submit-modal-input-sm"
                  min={1} max={500} value={maxTweets} onChange={e => setMaxTweets(parseInt(e.target.value) || 20)} />
                tweets
              </label>
              <label className="submit-modal-checkbox">
                <input type="checkbox" checked={includeRetweets} onChange={e => setIncludeRetweets(e.target.checked)} />
                Include retweets
              </label>
            </div>
          </div>
        )}

        {/* Tweet Form */}
        {action === 'tweet' && (
          <div className="submit-modal-fields">
            <input
              className="submit-modal-input"
              placeholder="https://x.com/user/status/123456... or tweet ID"
              value={tweetUrl} onChange={e => setTweetUrl(e.target.value)}
              autoFocus
            />
            <label className="submit-modal-option-label">
              Max
              <input type="number" className="submit-modal-input-sm"
                min={0} max={200} value={maxReplies} onChange={e => setMaxReplies(parseInt(e.target.value) || 20)} />
              replies
            </label>
          </div>
        )}

        {/* Timeline Form */}
        {action === 'timeline' && (
          <div className="submit-modal-fields">
            <div className="relative">
              <span className="submit-modal-at">@</span>
              <input className="submit-modal-input" style={{ paddingLeft: '1.75rem' }}
                placeholder="username" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
            </div>
            <div className="submit-modal-options">
              <label className="submit-modal-option-label">
                Max
                <input type="number" className="submit-modal-input-sm"
                  min={1} max={500} value={tlMaxTweets} onChange={e => setTlMaxTweets(parseInt(e.target.value) || 50)} />
                tweets
              </label>
              <label className="submit-modal-checkbox">
                <input type="checkbox" checked={includeReplies} onChange={e => setIncludeReplies(e.target.checked)} />
                Include replies
              </label>
            </div>
          </div>
        )}

        {/* Submit */}
        <div className="submit-modal-footer">
          <button type="submit" className="btn btn-accent btn-sm" disabled={isLoading}>
            <Send size={14} />
            {isLoading ? 'Submitting...' : 'Submit'}
          </button>
          {result && (
            <span className="submit-modal-success">
              <Check size={14} />
              Task {result.task_id.slice(0, 8)}... created
            </span>
          )}
          {error && (
            <span className="submit-modal-error">{error}</span>
          )}
        </div>
      </form>
    </Modal>
  )
}
