import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Clock, TrendingUp, TrendingDown, Minus, Trash2, Pause, Play, Send, Languages, Loader2, Heart, Eye, Repeat2, MessageSquare, BarChart3, Image } from 'lucide-react'
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { Markdown } from '@/components/ui/Markdown'
import {
  useGetTopicQuery,
  useGetTopicTrendQuery,
  useReanalyzeTopicMutation,
  useUpdateTopicMutation,
  useDeleteTopicMutation,
} from '@/store/api'
import type { TopicInsight } from '@/types/models'
import { useTimezone } from '@/hooks/useTimezone'

function normalizeInsights(data: { alerts?: unknown[]; insights?: unknown[] } | null): TopicInsight[] {
  const result: TopicInsight[] = []
  // New format: insights with sentiment
  if (data?.insights && Array.isArray(data.insights)) {
    for (const item of data.insights) {
      if (typeof item === 'object' && item !== null && 'text' in item) {
        const i = item as { text: string; sentiment?: string }
        result.push({ text: i.text, sentiment: (i.sentiment as TopicInsight['sentiment']) ?? 'neutral' })
      } else if (typeof item === 'string') {
        result.push({ text: item, sentiment: 'neutral' })
      }
    }
    return result
  }
  // Legacy format: alerts
  if (data?.alerts && Array.isArray(data.alerts)) {
    for (const item of data.alerts) {
      if (typeof item === 'object' && item !== null && 'message' in item) {
        const a = item as { level?: string; message: string }
        result.push({ text: a.message, sentiment: (a.level === 'critical' || a.level === 'warning') ? 'negative' : 'neutral' })
      } else if (typeof item === 'string') {
        result.push({ text: item, sentiment: 'neutral' })
      }
    }
    return result
  }
  return result
}

function fmtNum(n: unknown): string {
  if (n == null) return '-'
  const v = Number(n)
  if (isNaN(v)) return '-'
  if (v >= 100_000) return `${(v / 1000).toFixed(0)}k`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

/** Summary card with integrated chat — summary is the first "assistant" turn */
function SummaryChat({
  topicId,
  summary,
  translated,
  translating,
  onTranslate,
  cycleId,
  insights,
}: {
  topicId: string
  summary: string
  translated: string
  translating: boolean
  onTranslate: () => void
  cycleId?: string
  insights: TopicInsight[]
}) {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [])

  // auto-scroll when new messages arrive
  useEffect(() => {
    if (messages.length > 0) scrollToBottom()
  }, [messages, scrollToBottom])

  const send = async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')

    const userMsg: ChatMsg = { role: 'user', content: text }
    // Include the summary as the initial assistant context
    const contextMessages: ChatMsg[] = [
      { role: 'assistant', content: summary },
      ...messages,
      userMsg,
    ]
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '' }])
    setStreaming(true)

    try {
      const res = await fetch(`/api/topics/${topicId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: contextMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      })

      if (!res.body) throw new Error('No response body')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()!

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.t) {
              accumulated += evt.t
              setMessages((prev) => {
                const copy = [...prev]
                copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                return copy
              })
            }
            if (evt.error) {
              accumulated += `\n\n[Error: ${evt.error}]`
              setMessages((prev) => {
                const copy = [...prev]
                copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                return copy
              })
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'assistant', content: `Error: ${err}` }
        return copy
      })
    } finally {
      setStreaming(false)
    }
  }

  const hasChat = messages.length > 0

  return (
    <Card>
      <CardContent className="summary-chat-card">
        <CardHeader className="mb-3">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <CardDescription>Summary</CardDescription>
            <button
              className="topic-card-refresh"
              style={{ fontSize: '0.6875rem', padding: '3px 8px', gap: 4 }}
              onClick={onTranslate}
              disabled={translating}
            >
              {translating ? <Loader2 size={11} className="animate-spin" /> : <Languages size={11} />}
              {translated ? 'Original' : '翻译'}
            </button>
          </div>
        </CardHeader>

        {/* Scrollable area: insights + summary + chat messages */}
        <div ref={scrollRef} className="summary-chat-scroll">
          {/* Insights — above the summary */}
          {insights.length > 0 && (
            <div className="summary-insights">
              {insights.map((insight, i) => (
                <div key={i} className={`summary-insight ${insight.sentiment}`}>
                  {insight.sentiment === 'positive' ? <TrendingUp size={12} /> : insight.sentiment === 'negative' ? <TrendingDown size={12} /> : <Minus size={12} />}
                  <span>{insight.text}</span>
                </div>
              ))}
            </div>
          )}

          {/* Summary = first assistant turn */}
          <div className="summary-chat-summary">
            <Markdown>{translated || summary}</Markdown>
          </div>

          {cycleId && (
            <div style={{ marginTop: 12, fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', color: 'var(--ink-3)' }}>
              <Clock size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Cycle: {cycleId}
            </div>
          )}

          {/* Chat messages */}
          {hasChat && (
            <div className="summary-chat-divider">
              <span>Conversation</span>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`topic-chat-msg ${msg.role}`}>
              <div className="topic-chat-msg-content">
                {msg.role === 'assistant'
                  ? <Markdown>{msg.content || (streaming && i === messages.length - 1 ? '...' : '')}</Markdown>
                  : (msg.content || (streaming && i === messages.length - 1 ? '...' : ''))}
              </div>
            </div>
          ))}
        </div>

        {/* Chat input — always visible at the bottom */}
        <div className="summary-chat-input-row">
          <input
            className="topic-chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Ask about this analysis..."
            disabled={streaming}
          />
          <Button size="sm" onClick={send} disabled={streaming || !input.trim()}>
            <Send size={14} />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function formatDay(day: string): string {
  // Handle both "2026-02-11" and "2026-02-11 18:00" formats
  const d = new Date(day.includes(' ') ? day.replace(' ', 'T') : day + 'T00:00:00')
  if (isNaN(d.getTime())) return day
  const hasTime = day.includes(' ')
  if (hasTime) return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}h`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

type TrendKey = 'posts' | 'likes' | 'views'

const TREND_META: Record<TrendKey, { color: string }> = {
  posts: { color: 'var(--accent)' },
  likes: { color: 'var(--positive)' },
  views: { color: 'var(--blue)' },
}

/** Compute the latest day's value as delta */
function getLatestDelta(trend: { posts: number; likes: number; views: number }[] | undefined, key: TrendKey): number | null {
  if (!trend || trend.length === 0) return null
  return trend[trend.length - 1][key]
}

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="trend-tooltip">
      <div className="trend-tooltip-date">{label}</div>
      <div className="trend-tooltip-row">
        <span className="trend-tooltip-value">{fmtNum(payload[0].value)}</span>
      </div>
    </div>
  )
}

/** Compact sparkline chart that expands below the clicked stat */
function TrendSparkline({ trend, metricKey, anchorLeft }: { trend: { day: string; posts: number; likes: number; views: number }[]; metricKey: TrendKey; anchorLeft: number }) {
  const meta = TREND_META[metricKey]
  const chartData = trend.map(d => ({ ...d, day: formatDay(d.day) }))

  return (
    <div className="trend-sparkline" style={{ marginLeft: Math.max(0, anchorLeft - 120) }}>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${metricKey}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={meta.color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={meta.color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="day"
            tick={{ fill: 'var(--ink-3)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<TrendTooltip />} />
          <Area type="monotone" dataKey={metricKey} stroke={meta.color} strokeWidth={2} fill={`url(#grad-${metricKey})`} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function TopicDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: topic, isLoading, isError } = useGetTopicQuery(id ?? '', { skip: !id, pollingInterval: 10000 })
  const { data: trend } = useGetTopicTrendQuery(id ?? '', { skip: !id })
  const [reanalyzeTopic, { isLoading: isReanalyzing }] = useReanalyzeTopicMutation()
  const [updateTopic] = useUpdateTopicMutation()
  const [deleteTopic] = useDeleteTopicMutation()
  const { fmt } = useTimezone()
  const [translated, setTranslated] = useState('')
  const [translating, setTranslating] = useState(false)
  const [expandedMetric, setExpandedMetric] = useState<TrendKey | null>(null)
  const [anchorLeft, setAnchorLeft] = useState(0)
  const statsRef = useRef<HTMLDivElement>(null)

  const handleTranslate = useCallback(async (text: string) => {
    if (translating || translated) { setTranslated(''); return }
    setTranslating(true)
    setTranslated('')
    try {
      const res = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, target: 'zh' }),
      })
      if (!res.body) return
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = '', acc = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.t) { acc += evt.t; setTranslated(acc) }
          } catch { /* skip */ }
        }
      }
    } catch { setTranslated('Translation failed.') }
    finally { setTranslating(false) }
  }, [translating, translated])

  if (isLoading) {
    return (
      <div className="stack rise">
        <div style={{ height: 32 }}><Skeleton className="w-48 h-full" /></div>
        <div style={{ height: 256 }}><Skeleton className="w-full h-full" /></div>
      </div>
    )
  }

  if (isError || !topic || ('error' in topic)) {
    return (
      <div className="stack rise">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} /> Back
        </Button>
        <p style={{ color: 'var(--negative)' }}>Topic not found</p>
      </div>
    )
  }

  const insights = normalizeInsights(topic.summary_data)
  const metrics = (topic.summary_data?.metrics ?? {}) as Record<string, unknown>
  const hasTrend = trend && trend.length >= 2

  const toggleMetric = (key: TrendKey, e: React.MouseEvent) => {
    if (expandedMetric === key) {
      setExpandedMetric(null)
    } else {
      // Compute offset relative to the stats bar
      const statEl = e.currentTarget as HTMLElement
      const barEl = statsRef.current
      if (barEl) {
        const barRect = barEl.getBoundingClientRect()
        const statRect = statEl.getBoundingClientRect()
        setAnchorLeft(statRect.left - barRect.left + statRect.width / 2)
      }
      setExpandedMetric(key)
    }
  }

  // Compute deltas from trend data
  const postsDelta = getLatestDelta(trend, 'posts')
  const likesDelta = getLatestDelta(trend, 'likes')
  const viewsDelta = getLatestDelta(trend, 'views')

  const handleTogglePause = async () => {
    await updateTopic({ id: topic.id, status: topic.status === 'active' ? 'paused' : 'active' })
  }

  const handleDelete = async () => {
    await deleteTopic(topic.id)
    navigate('/')
  }

  return (
    <div className="topic-detail rise">
      {/* Header */}
      <div className="topic-detail-header">
        <div className="topic-detail-title">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft size={16} />
          </Button>
          <div className="topic-card-icon-box" style={{ width: 40, height: 40, borderRadius: 12, fontSize: 18 }}>
            {topic.icon}
          </div>
          <h1>{topic.name}</h1>
          <div className={`topic-status-pill ${topic.status === 'active' ? 'active' : 'paused'}`}>
            <span className="topic-status-dot">
              <span className="topic-status-dot-inner" />
              {topic.status === 'active' && <span className="topic-status-dot-ring" />}
            </span>
            {topic.status === 'active' ? 'Live' : 'Paused'}
          </div>
        </div>
        <div className="topic-detail-actions">
          <button className="topic-card-refresh" onClick={() => reanalyzeTopic(topic.id)} disabled={isReanalyzing}>
            <RefreshCw size={13} className={isReanalyzing ? 'animate-spin' : ''} />
            {isReanalyzing ? 'Analyzing...' : 'Reanalyze'}
          </button>
          <Button size="sm" variant="ghost" onClick={handleTogglePause}>
            {topic.status === 'active' ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDelete} style={{ color: 'var(--negative)' }}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Compact info + metrics bar */}
      <div ref={statsRef} className="topic-detail-stats pop" style={{ animationDelay: '80ms' }}>
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Created</span>
          <span className="topic-detail-stat-value">{fmt(topic.created_at)}</span>
        </div>
        <div className="topic-detail-stat-sep" />
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Last Crawl</span>
          <span className="topic-detail-stat-value">{fmt(topic.last_crawl_at)}</span>
        </div>
        <div className="topic-detail-stat-sep" />
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Platforms</span>
          <span style={{ display: 'flex', gap: 4 }}>
            {(topic.platforms ?? []).map((p) => (
              <span key={p} className="topic-tag platform">{(p ?? '').toUpperCase()}</span>
            ))}
          </span>
        </div>
        <div className="topic-detail-stat-sep" />
        <div
          className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'posts' ? 'expanded' : ''}`}
          onClick={(e) => hasTrend && toggleMetric('posts', e)}
        >
          <BarChart3 size={13} />
          <span className="topic-detail-stat-num">{fmtNum(topic.total_contents)}</span>
          <span className="topic-detail-stat-label">posts</span>
          {postsDelta != null && postsDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(postsDelta)}</span>}
        </div>
        {metrics.total_likes != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'likes' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('likes', e)}
            >
              <Heart size={12} />
              <span className="topic-detail-stat-num">{fmtNum(metrics.total_likes)}</span>
              {likesDelta != null && likesDelta > 0 && <span className="topic-detail-stat-delta positive">+{fmtNum(likesDelta)}</span>}
            </div>
          </>
        )}
        {metrics.total_views != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'views' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('views', e)}
            >
              <Eye size={12} />
              <span className="topic-detail-stat-num">{fmtNum(metrics.total_views)}</span>
              {viewsDelta != null && viewsDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(viewsDelta)}</span>}
            </div>
          </>
        )}
        {metrics.total_retweets != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div className="topic-detail-stat highlight">
              <Repeat2 size={12} />
              <span className="topic-detail-stat-num">{fmtNum(metrics.total_retweets)}</span>
            </div>
          </>
        )}
        {metrics.total_replies != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div className="topic-detail-stat highlight">
              <MessageSquare size={12} />
              <span className="topic-detail-stat-num">{fmtNum(metrics.total_replies)}</span>
            </div>
          </>
        )}
        {metrics.with_media_pct != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div className="topic-detail-stat highlight">
              <Image size={12} />
              <span className="topic-detail-stat-num">{fmtNum(metrics.with_media_pct)}%</span>
            </div>
          </>
        )}
      </div>

      {/* Expanded sparkline — slides open below stats bar */}
      {expandedMetric && hasTrend && (
        <TrendSparkline trend={trend} metricKey={expandedMetric} anchorLeft={anchorLeft} />
      )}

      {/* Keywords */}
      {(topic.keywords ?? []).length > 0 && (
        <div className="topic-card-tags" style={{ padding: 0 }}>
          {(topic.keywords ?? []).map((kw) => <span key={kw} className="topic-tag">#{kw}</span>)}
        </div>
      )}

      {/* Summary + Chat (integrated) */}
      {topic.last_summary && (
        <SummaryChat
          topicId={topic.id}
          summary={topic.last_summary}
          translated={translated}
          translating={translating}
          onTranslate={() => handleTranslate(topic.last_summary!)}
          cycleId={topic.summary_data?.cycle_id}
          insights={insights}
        />
      )}

      {/* Raw data */}
      {topic.summary_data && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', cursor: 'pointer', color: 'var(--ink-3)', padding: '8px 0' }}>
            Raw summary data
          </summary>
          <pre style={{
            fontFamily: "'Space Mono', monospace",
            fontSize: '0.6875rem',
            overflow: 'auto',
            padding: 16,
            marginTop: 8,
            background: 'var(--glass)',
            backdropFilter: 'blur(12px)',
            borderRadius: 14,
            maxHeight: 400,
            border: '1px solid var(--glass-border)',
            color: 'var(--ink-2)',
          }}>
            {JSON.stringify(topic.summary_data, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
