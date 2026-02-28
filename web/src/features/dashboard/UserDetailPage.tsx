import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Clock, TrendingUp, TrendingDown, Minus, Trash2, Pause, Play, Send, Languages, Loader2, Heart, Eye, Repeat2, MessageSquare, BarChart3, Image, ExternalLink, Pencil, X, Check, CheckCircle } from 'lucide-react'
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { Markdown } from '@/components/ui/Markdown'
import {
  useGetUserQuery,
  useGetUserTrendQuery,
  useReanalyzeUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useDetachUserMutation,
  useGetUserProgressQuery,
  useGetUserChatHistoryQuery,
} from '@/store/api'
import type { TopicInsight, ProgressTask } from '@/types/models'
import { useTimezone } from '@/hooks/useTimezone'
import { useSSEChat } from '@/hooks/useSSEChat'
import { CreateEditModal } from './CreateEditModal'

function normalizeInsights(data: { alerts?: unknown[]; insights?: unknown[] } | null): TopicInsight[] {
  const result: TopicInsight[] = []
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
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 100_000) return `${(v / 1000).toFixed(0)}k`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

function SummaryChat({
  userId,
  summary,
  translated,
  translating,
  onTranslate,
  cycleId,
  insights,
}: {
  userId: string
  summary: string
  translated: string
  translating: boolean
  onTranslate: () => void
  cycleId?: string
  insights: TopicInsight[]
}) {
  const { data: chatHistory } = useGetUserChatHistoryQuery(userId)
  const restoredMessages = useMemo(
    () => chatHistory?.messages?.map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })) ?? [],
    [chatHistory],
  )

  const buildBody = useCallback(
    (msgs: { role: string; content: string }[]) => ({
      messages: [{ role: 'assistant', content: summary }, ...msgs]
        .map((m) => ({ role: m.role, content: m.content })),
    }),
    [summary],
  )

  const { messages, input, setInput, streaming, send, handleKeyDown, scrollRef } = useSSEChat({
    endpoint: `/api/users/${userId}/chat`,
    buildBody,
    mode: 'direct',
    initialMessages: restoredMessages,
  })

  const hasChat = messages.length > 0

  return (
    <Card>
      <CardContent className="summary-chat-card">
        <CardHeader className="mb-3">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <CardDescription>Summary</CardDescription>
            <button
              className="topic-card-refresh"
              onClick={onTranslate}
              disabled={translating}
              title={translated ? 'Show original' : 'Translate to Chinese'}
            >
              {translating ? <Loader2 size={11} className="animate-spin" /> : <Languages size={11} />}
            </button>
          </div>
        </CardHeader>

        <div className="summary-chat-scroll">
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

          <div className="summary-chat-summary">
            <Markdown>{translated || summary}</Markdown>
          </div>

          {cycleId && (
            <div style={{ marginTop: 12, fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', color: 'var(--ink-3)' }}>
              <Clock size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
              Cycle: {cycleId}
            </div>
          )}

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
          <div ref={scrollRef} />
        </div>

        <div className="summary-chat-input-row">
          <textarea
            className="topic-chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this user's content..."
            disabled={streaming}
            rows={1}
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
  const d = new Date(day.includes(' ') ? day.replace(' ', 'T') : day + 'T00:00:00')
  if (isNaN(d.getTime())) return day
  const hasTime = day.includes(' ')
  if (hasTime) return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}h`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

type TrendKey = 'posts' | 'likes' | 'views' | 'retweets' | 'replies'

const TREND_META: Record<TrendKey, { color: string }> = {
  posts: { color: 'var(--accent)' },
  likes: { color: 'var(--pink)' },
  views: { color: 'var(--cyan)' },
  retweets: { color: 'var(--warning)' },
  replies: { color: 'var(--lavender)' },
}

type TrendPoint = { posts: number; likes: number; views: number; retweets: number; replies: number; media_posts: number }

function getTrendTotal(trend: TrendPoint[] | undefined, key: keyof TrendPoint): number | null {
  if (!trend || trend.length === 0) return null
  return trend.reduce((sum, d) => sum + d[key], 0)
}

function getLatestDelta(trend: TrendPoint[] | undefined, key: keyof TrendPoint): number | null {
  if (!trend || trend.length === 0) return null
  return trend[trend.length - 1][key]
}

function TrendTooltip({ active, payload, label, metricLabel }: { active?: boolean; payload?: { value: number }[]; label?: string; metricLabel?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="trend-tooltip">
      <div className="trend-tooltip-date">{label}</div>
      <div className="trend-tooltip-row">
        <span className="trend-tooltip-value">{fmtNum(payload[0].value)} {metricLabel ?? ''}</span>
      </div>
    </div>
  )
}

function TrendSparkline({ trend, metricKey, anchorLeft }: { trend: (TrendPoint & { day: string })[]; metricKey: TrendKey; anchorLeft: number }) {
  const meta = TREND_META[metricKey]
  const chartData = trend.map(d => ({ ...d, day: formatDay(d.day) }))

  return (
    <div className="trend-sparkline" style={{ marginLeft: Math.max(0, anchorLeft - 120) }}>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 20, right: 8, left: 8, bottom: 0 }}>
          <XAxis
            dataKey="day"
            tick={{ fill: 'var(--ink-3)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<TrendTooltip metricLabel={metricKey} />} />
          <Bar dataKey={metricKey} fill={meta.color} opacity={0.7} radius={[4, 4, 0, 0]} label={{ position: 'top', fill: 'var(--ink-2)', fontSize: 11, formatter: fmtNum }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function getTaskIcon(task: ProgressTask): string {
  if (task.label?.startsWith('searcher:')) return '🌐'
  const action = task.payload?.action || task.progress?.action
  if (action === 'timeline') return '📋'
  if (action === 'search') return '🔍'
  if (action === 'tweet') return '💬'
  return '⚡'
}

function getTaskLabel(task: ProgressTask): string {
  const action = task.payload?.action
  if (task.label?.startsWith('searcher:') && task.payload?.query) return `Web: ${task.payload.query}`
  if (action === 'timeline' && task.payload?.username) return `Timeline @${task.payload.username}`
  if (action === 'search' && task.payload?.query) return `Search: ${task.payload.query}`
  if (action === 'tweet') return `Tweet detail`
  return task.label || 'Task'
}

function getTaskProgressPct(task: ProgressTask): number | null {
  const p = task.progress
  if (!p) return null
  if (p.action === 'timeline' && p.target_new && p.target_new > 0) {
    return Math.min(100, Math.round(((p.new_count || 0) / p.target_new) * 100))
  }
  return null
}

function UserProgressTasks({ entityId, onRetry }: { entityId: string; onRetry?: () => void }) {
  const { data } = useGetUserProgressQuery(entityId, { pollingInterval: 2000 })
  const [expanded, setExpanded] = useState(true)

  if (!data?.progress) return null

  // Show brief "done" badge
  if (data.progress.phase === 'done') {
    return (
      <div className="progress-tasks-section pop progress-done done" style={{ animationDelay: '120ms' }}>
        <div className="progress-tasks-header">
          <div className="progress-tasks-header-left">
            <CheckCircle size={14} />
            <span className="progress-tasks-phase">Analysis complete</span>
          </div>
        </div>
      </div>
    )
  }

  if (data.tasks.length === 0 && !['analyzing', 'crawling', 'summarizing', 'error'].includes(data.progress.phase)) return null

  const phase = data.progress.phase
  const total = Number(data.progress.total) || 0
  const done = Number(data.progress.done) || 0
  const overallPct = total > 0 ? Math.round((done / total) * 100) : 0
  const step = data.progress.step

  return (
    <div className={`progress-tasks-section pop ${phase}`} style={{ animationDelay: '120ms' }}>
      {data.tasks.length > 0 ? (
        <button className="progress-tasks-header" onClick={() => setExpanded((p) => !p)}>
          <div className="progress-tasks-header-left">
            {phase === 'analyzing' && <Loader2 size={14} className="progress-spin" />}
            {phase === 'crawling' && <RefreshCw size={14} className="progress-spin" />}
            {phase === 'summarizing' && <TrendingUp size={14} className="progress-spin" />}
            {phase === 'error' && <span style={{ color: 'var(--negative)' }}>!</span>}
            <span className="progress-tasks-phase">
              {phase === 'analyzing' && 'Analyzing...'}
              {phase === 'crawling' && `Crawling ${done}/${total}`}
              {phase === 'summarizing' && 'Summarizing...'}
              {phase === 'error' && `Error: ${data.progress.error_msg || 'Unknown'}`}
            </span>
            {step && (phase === 'analyzing' || phase === 'summarizing') && (
              <span className="progress-tasks-step">{step}</span>
            )}
            {phase === 'error' && onRetry && (
              <button
                className="progress-retry-btn"
                onClick={(e) => { e.stopPropagation(); onRetry() }}
              >
                <RefreshCw size={10} /> Retry
              </button>
            )}
          </div>
          {phase === 'crawling' && total > 0 && (
            <div className="progress-tasks-overall-bar">
              <div className="progress-tasks-overall-fill" style={{ width: `${overallPct}%` }} />
            </div>
          )}
          <span className="progress-tasks-chevron">{expanded ? '▾' : '▸'}</span>
        </button>
      ) : (
        <div className="progress-tasks-header">
          <div className="progress-tasks-header-left">
            {phase === 'analyzing' && <Loader2 size={14} className="progress-spin" />}
            {phase === 'summarizing' && <TrendingUp size={14} className="progress-spin" />}
            {phase === 'error' && <span style={{ color: 'var(--negative)' }}>!</span>}
            <span className="progress-tasks-phase">
              {phase === 'analyzing' && 'Analyzing...'}
              {phase === 'summarizing' && 'Summarizing...'}
              {phase === 'error' && `Error: ${data.progress.error_msg || 'Unknown'}`}
            </span>
            {step && <span className="progress-tasks-step">{step}</span>}
            {phase === 'error' && onRetry && (
              <button
                className="progress-retry-btn"
                onClick={(e) => { e.stopPropagation(); onRetry() }}
              >
                <RefreshCw size={10} /> Retry
              </button>
            )}
          </div>
        </div>
      )}
      {expanded && data.tasks.length > 0 && (
        <div className="progress-tasks-list">
          {data.tasks.map((task) => {
            const pct = getTaskProgressPct(task)
            const isDone = task.status === 'completed'
            const isFailed = task.status === 'failed'
            const isRunning = task.status === 'running'
            return (
              <div key={task.id} className={`progress-task-item ${isDone ? 'done' : ''} ${isFailed ? 'failed' : ''} ${isRunning ? 'running' : ''}`}>
                <div className="progress-task-row">
                  <span className="progress-task-icon">{getTaskIcon(task)}</span>
                  <span className="progress-task-label">{getTaskLabel(task)}</span>
                  <span className={`progress-task-status ${task.status}`}>
                    {isDone && '✓'}
                    {isFailed && '✗'}
                    {isRunning && <Loader2 size={10} className="progress-spin" />}
                    {task.status === 'pending' && '○'}
                  </span>
                </div>
                {task.progress?.message && isRunning && (
                  <div className="progress-task-message">{task.progress.message}</div>
                )}
                {pct !== null && isRunning && (
                  <div className="progress-task-bar">
                    <div className="progress-task-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [fastPoll, setFastPoll] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const { data: user, isLoading, isError } = useGetUserQuery(id ?? '', { skip: !id, pollingInterval: fastPoll ? 3000 : 10000 })
  const { data: trend } = useGetUserTrendQuery(id ?? '', { skip: !id })
  const [reanalyzeUser, { isLoading: isReanalyzing }] = useReanalyzeUserMutation()
  const [updateUser] = useUpdateUserMutation()
  const [deleteUser] = useDeleteUserMutation()
  const [detachUser] = useDetachUserMutation()
  const { fmt } = useTimezone()
  const [translated, setTranslated] = useState('')
  const [translating, setTranslating] = useState(false)
  const [expandedMetric, setExpandedMetric] = useState<TrendKey | null>(null)
  const [anchorLeft, setAnchorLeft] = useState(0)
  const [showMediaPie, setShowMediaPie] = useState(false)
  const [editingTopics, setEditingTopics] = useState(false)
  const [pendingDetach, setPendingDetach] = useState<Set<string>>(new Set())
  const statsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const active = user?.progress?.phase && user.progress.phase !== 'done' && user.progress.phase !== 'error'
    setFastPoll(!!active)
  }, [user?.progress?.phase])

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

  if (isError || !user || ('error' in user)) {
    return (
      <div className="stack rise">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} /> Back
        </Button>
        <p style={{ color: 'var(--negative)' }}>User not found</p>
      </div>
    )
  }

  const insights = normalizeInsights(user.summary_data)
  const metrics = (user.summary_data?.metrics ?? {}) as Record<string, unknown>
  const hasTrend = trend && trend.length >= 1

  const toggleMetric = (key: TrendKey, e: React.MouseEvent) => {
    setShowMediaPie(false)
    if (expandedMetric === key) {
      setExpandedMetric(null)
    } else {
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

  const toggleMediaPie = (e: React.MouseEvent) => {
    setExpandedMetric(null)
    const statEl = e.currentTarget as HTMLElement
    const barEl = statsRef.current
    if (barEl) {
      const barRect = barEl.getBoundingClientRect()
      const statRect = statEl.getBoundingClientRect()
      setAnchorLeft(statRect.left - barRect.left + statRect.width / 2)
    }
    setShowMediaPie((prev) => !prev)
  }

  const postsDelta = getLatestDelta(trend, 'posts')
  const likesDelta = getLatestDelta(trend, 'likes')
  const viewsDelta = getLatestDelta(trend, 'views')
  const retweetsDelta = getLatestDelta(trend, 'retweets')
  const repliesDelta = getLatestDelta(trend, 'replies')
  const likesTotal = getTrendTotal(trend, 'likes')
  const viewsTotal = getTrendTotal(trend, 'views')
  const retweetsTotal = getTrendTotal(trend, 'retweets')
  const repliesTotal = getTrendTotal(trend, 'replies')
  const mediaPostsTotal = getTrendTotal(trend, 'media_posts')
  const postsTotal = getTrendTotal(trend, 'posts')
  const mediaPct = (postsTotal && mediaPostsTotal != null) ? Math.round(mediaPostsTotal * 100 / postsTotal) : null

  const handleTogglePause = async () => {
    await updateUser({ id: user.id, status: user.status === 'active' ? 'paused' : 'active' })
  }

  const handleDelete = async () => {
    await deleteUser(user.id)
    navigate('/')
  }

  const handleDetach = async (topicId: string) => {
    await detachUser({ userId: user.id, topicId })
  }

  // Crawl progress from summary_data
  const crawlProgress = (user.summary_data as Record<string, unknown>)?.crawl_progress as
    { timeline_exhausted?: boolean; total_known_tweets?: number } | undefined

  return (
    <div className="topic-detail rise">
      {/* Header */}
      <div className="topic-detail-header">
        <div className="topic-detail-title">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft size={16} />
          </Button>
          <div className="topic-card-icon-box" style={{ width: 40, height: 40, borderRadius: 12, fontSize: 18 }}>
            👤
          </div>
          <div>
            <h1>{user.name}</h1>
            {user.username && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '0.75rem', color: 'var(--ink-3)' }}>
                @{user.username}
              </span>
            )}
          </div>
          <div className={`topic-status-pill ${user.status === 'active' ? 'active' : 'paused'}`}>
            <span className="topic-status-dot">
              <span className="topic-status-dot-inner" />
              {user.status === 'active' && <span className="topic-status-dot-ring" />}
            </span>
            {user.status === 'active' ? 'Live' : 'Paused'}
          </div>
        </div>
        <div className="topic-detail-actions">
          <button className="topic-card-refresh" onClick={() => setShowEdit(true)} title="Edit">
            <Pencil size={13} />
          </button>
          <button className="topic-card-refresh" onClick={() => reanalyzeUser(user.id)} disabled={isReanalyzing || fastPoll} title="Reanalyze">
            <RefreshCw size={13} className={isReanalyzing || fastPoll ? 'animate-spin' : ''} />
          </button>
          {user.profile_url && (
            <a href={user.profile_url} target="_blank" rel="noreferrer" className="topic-card-refresh" title="Open profile">
              <ExternalLink size={13} />
            </a>
          )}
          <Button size="sm" variant="ghost" onClick={handleTogglePause}>
            {user.status === 'active' ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDelete} style={{ color: 'var(--negative)' }}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Compact info + metrics bar */}
      <div className="topic-detail-stats-wrapper">
      <div ref={statsRef} className="topic-detail-stats pop" style={{ animationDelay: '80ms' }}>
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Created</span>
          <span className="topic-detail-stat-value">{fmt(user.created_at)}</span>
        </div>
        <div className="topic-detail-stat-sep" />
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Last Crawl</span>
          <span className="topic-detail-stat-value">{fmt(user.last_crawl_at)}</span>
        </div>
        <div className="topic-detail-stat-sep" />
        <div className="topic-detail-stat">
          <span className="topic-detail-stat-label">Platform</span>
          <span className="topic-tag platform">{(user.platform ?? '').toUpperCase()}</span>
        </div>
        {crawlProgress?.timeline_exhausted != null && (
          <>
            <div className="topic-detail-stat-sep" />
            <div className="topic-detail-stat">
              <span className="topic-detail-stat-label">Timeline</span>
              <span className="topic-detail-stat-value">
                {crawlProgress.timeline_exhausted ? 'Fully crawled' : 'In progress'}
              </span>
            </div>
          </>
        )}
        <div className="topic-detail-stat-sep" />
        <div
          className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'posts' ? 'expanded' : ''}`}
          onClick={(e) => hasTrend && toggleMetric('posts', e)}
        >
          <BarChart3 size={13} />
          <span className="topic-detail-stat-num">{fmtNum(postsTotal ?? user.total_contents)}</span>
          <span className="topic-detail-stat-label">posts</span>
          {postsDelta != null && postsDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(postsDelta)}</span>}
        </div>
        {(likesTotal != null || metrics.total_likes != null) && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'likes' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('likes', e)}
            >
              <Heart size={12} />
              <span className="topic-detail-stat-num">{fmtNum(likesTotal ?? metrics.total_likes)}</span>
              {likesDelta != null && likesDelta > 0 && <span className="topic-detail-stat-delta positive">+{fmtNum(likesDelta)}</span>}
            </div>
          </>
        )}
        {(viewsTotal != null || metrics.total_views != null) && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'views' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('views', e)}
            >
              <Eye size={12} />
              <span className="topic-detail-stat-num">{fmtNum(viewsTotal ?? metrics.total_views)}</span>
              {viewsDelta != null && viewsDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(viewsDelta)}</span>}
            </div>
          </>
        )}
        {(retweetsTotal != null || metrics.total_retweets != null) && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'retweets' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('retweets', e)}
            >
              <Repeat2 size={12} />
              <span className="topic-detail-stat-num">{fmtNum(retweetsTotal ?? metrics.total_retweets)}</span>
              {retweetsDelta != null && retweetsDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(retweetsDelta)}</span>}
            </div>
          </>
        )}
        {(repliesTotal != null || metrics.total_replies != null) && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${hasTrend ? 'clickable' : ''} ${expandedMetric === 'replies' ? 'expanded' : ''}`}
              onClick={(e) => hasTrend && toggleMetric('replies', e)}
            >
              <MessageSquare size={12} />
              <span className="topic-detail-stat-num">{fmtNum(repliesTotal ?? metrics.total_replies)}</span>
              {repliesDelta != null && repliesDelta > 0 && <span className="topic-detail-stat-delta">+{fmtNum(repliesDelta)}</span>}
            </div>
          </>
        )}
        {(mediaPct != null || metrics.with_media_pct != null) && (
          <>
            <div className="topic-detail-stat-sep" />
            <div
              className={`topic-detail-stat highlight ${mediaPostsTotal != null ? 'clickable' : ''} ${showMediaPie ? 'expanded' : ''}`}
              onClick={(e) => mediaPostsTotal != null && toggleMediaPie(e)}
            >
              <Image size={12} />
              <span className="topic-detail-stat-num">{mediaPct ?? fmtNum(metrics.with_media_pct)}%</span>
            </div>
          </>
        )}
      </div>

      {expandedMetric && hasTrend && (
        <TrendSparkline trend={trend} metricKey={expandedMetric} anchorLeft={anchorLeft} />
      )}

      {showMediaPie && mediaPostsTotal != null && postsTotal != null && postsTotal > 0 && (() => {
        const pct = Math.round(mediaPostsTotal * 100 / postsTotal)
        const textOnly = postsTotal - mediaPostsTotal
        return (
          <div className="trend-sparkline media-pie" style={{ marginLeft: Math.max(0, anchorLeft - 120) }}>
            <div className="media-pie-chart">
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Media', value: mediaPostsTotal },
                      { name: 'Text only', value: textOnly },
                    ]}
                    cx="50%"
                    cy="50%"
                    innerRadius={36}
                    outerRadius={60}
                    dataKey="value"
                    stroke="none"
                    startAngle={90}
                    endAngle={-270}
                    animationDuration={400}
                  >
                    <Cell fill="var(--accent)" />
                    <Cell fill="var(--ink-4)" />
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null
                      const d = payload[0]
                      return (
                        <div className="trend-tooltip">
                          <div className="trend-tooltip-date">{d.name}</div>
                          <div className="trend-tooltip-row">
                            <span className="trend-tooltip-value">{d.value} posts</span>
                          </div>
                        </div>
                      )
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="media-pie-center">
                <span className="media-pie-pct">{pct}%</span>
                <span className="media-pie-label">media</span>
              </div>
            </div>
            <div className="media-pie-legend">
              <div className="media-pie-legend-row">
                <span className="media-pie-dot" style={{ background: 'var(--accent)' }} />
                <span className="media-pie-legend-label">Media</span>
                <span className="media-pie-legend-value">{mediaPostsTotal}</span>
              </div>
              <div className="media-pie-legend-row">
                <span className="media-pie-dot" style={{ background: 'var(--ink-4)' }} />
                <span className="media-pie-legend-label">Text only</span>
                <span className="media-pie-legend-value">{textOnly}</span>
              </div>
            </div>
          </div>
        )
      })()}
      </div>

      {/* Attached Topics */}
      {user.topics && user.topics.length > 0 && (
        <div className="topic-card-tags" style={{ padding: 0, position: 'relative' }}>
          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '0.6875rem', color: 'var(--ink-3)', marginRight: 8 }}>Topics:</span>
          {user.topics.map((t) => (
            <span
              key={t.id}
              className={`topic-tag${pendingDetach.has(t.id) ? ' detach-pending' : ''}`}
              style={{ cursor: editingTopics ? undefined : 'pointer' }}
              onClick={() => { if (!editingTopics) navigate(`/topic/${t.id}`) }}
            >
              {t.icon} {t.name}
              {editingTopics && (
                <button
                  className="topic-card-refresh"
                  style={{ marginLeft: 4, padding: 0, minWidth: 0 }}
                  onClick={(e) => {
                    e.stopPropagation()
                    setPendingDetach((prev) => {
                      const next = new Set(prev)
                      if (next.has(t.id)) next.delete(t.id)
                      else next.add(t.id)
                      return next
                    })
                  }}
                  title={pendingDetach.has(t.id) ? 'Undo remove' : 'Remove'}
                >
                  {pendingDetach.has(t.id) ? <span style={{ fontSize: 10 }}>↩</span> : <X size={10} />}
                </button>
              )}
            </span>
          ))}
          {!editingTopics ? (
            <button
              className="topic-card-refresh"
              style={{ marginLeft: 'auto' }}
              onClick={() => setEditingTopics(true)}
              title="Edit topics"
            >
              <Pencil size={11} />
            </button>
          ) : (
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
              <button
                className="topic-card-refresh"
                title="Cancel"
                onClick={() => { setEditingTopics(false); setPendingDetach(new Set()) }}
              >
                <X size={12} />
              </button>
              <button
                className="topic-card-refresh"
                style={{ color: pendingDetach.size > 0 ? 'var(--negative)' : 'var(--ink-3)' }}
                title={`Confirm (remove ${pendingDetach.size})`}
                disabled={pendingDetach.size === 0}
                onClick={async () => {
                  for (const tid of pendingDetach) {
                    await handleDetach(tid)
                  }
                  setPendingDetach(new Set())
                  setEditingTopics(false)
                }}
              >
                <Check size={12} />
              </button>
            </span>
          )}
        </div>
      )}

      {/* Active Progress Tasks */}
      <UserProgressTasks entityId={user.id} onRetry={() => reanalyzeUser(user.id)} />

      {/* Summary + Chat */}
      {user.last_summary && (
        <SummaryChat
          userId={user.id}
          summary={user.last_summary}
          translated={translated}
          translating={translating}
          onTranslate={() => handleTranslate(user.last_summary!)}
          cycleId={user.summary_data?.cycle_id}
          insights={insights}
        />
      )}

      {/* Raw data */}
      {user.summary_data && (
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
            {JSON.stringify(user.summary_data, null, 2)}
          </pre>
        </details>
      )}
      <CreateEditModal open={showEdit} onClose={() => setShowEdit(false)} editEntity={user} />
    </div>
  )
}
