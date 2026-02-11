import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Pin, RefreshCw,
  AlertTriangle, Info, AlertCircle,
  Sparkles, Send, Loader2,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import {
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useReanalyzeTopicMutation,
  useReorderTopicsMutation,
} from '@/store/api'
import type { Topic, TopicAlert, TopicPipeline } from '@/types/models'
import { useFlip } from '@/hooks/useFlip'
import { useZoneDrag, type Zone } from '@/hooks/useZoneDrag'

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

// ─── Animated Number ──────────────────────────────────────────

function AnimatedNum({ to, dur = 950 }: { to: number; dur?: number }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const s = performance.now()
    const go = (n: number) => {
      const p = Math.min((n - s) / dur, 1)
      setV(Math.round((1 - Math.pow(1 - p, 4)) * to))
      if (p < 1) requestAnimationFrame(go)
    }
    requestAnimationFrame(go)
  }, [to, dur])
  return <>{v}</>
}

// ─── Helpers ──────────────────────────────────────────────────

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function normalizeAlert(alert: TopicAlert): { level: string; message: string } {
  if (typeof alert === 'string') return { level: 'info', message: alert }
  return alert
}

function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^>\s+/gm, '')
    .replace(/\n{2,}/g, ' ')
    .replace(/\n/g, ' ')
    .trim()
}

function fmtNum(n: number): string {
  if (n >= 100_000) return `${(n / 1000).toFixed(0)}k`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

interface CardMetric {
  label: string
  value: string | number
  color?: string
  sub?: string
  subColor?: string
  subBg?: string
  animate?: boolean
}

function extractCardMetrics(metrics: Record<string, unknown>): CardMetric[] {
  const out: CardMetric[] = []
  const posts = metrics.total_contents
  if (posts != null) out.push({ label: 'Posts', value: Number(posts), animate: true })
  const likes = Number(metrics.total_likes ?? 0)
  const retweets = Number(metrics.total_retweets ?? 0)
  const replies = Number(metrics.total_replies ?? 0)
  const totalEngagement = likes + retweets + replies
  if (totalEngagement > 0) out.push({ label: 'Engagement', value: fmtNum(totalEngagement), color: 'var(--accent)' })
  const views = metrics.total_views
  if (views != null && Number(views) > 0) out.push({ label: 'Views', value: fmtNum(Number(views)) })
  const mediaPct = metrics.with_media_pct
  if (mediaPct != null && out.length < 4) out.push({ label: 'Media', value: `${mediaPct}%` })
  const topAuthor = metrics.top_author as string | undefined
  if (topAuthor && out.length < 4) out.push({ label: 'Top Author', value: `@${topAuthor}` })
  return out.slice(0, 4)
}

// ─── Pipeline Badge ──────────────────────────────────────────

function PipelineBadge({ pipeline }: { pipeline: TopicPipeline }) {
  const { phase, total, done } = pipeline

  if (phase === 'analyzing') {
    return (
      <div className="pipeline-badge analyzing">
        <Loader2 size={12} className="pipeline-spin" />
        <span>Analyzing topic data...</span>
      </div>
    )
  }

  if (phase === 'crawling') {
    const t = Number(total) || 0
    const d = Number(done) || 0
    const pct = t > 0 ? Math.round((d / t) * 100) : 0
    return (
      <div className="pipeline-badge crawling">
        <RefreshCw size={12} className="pipeline-spin" />
        <span>Crawling {d}/{t}</span>
        <div className="pipeline-bar">
          <div className="pipeline-bar-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
    )
  }

  if (phase === 'summarizing') {
    return (
      <div className="pipeline-badge summarizing">
        <Sparkles size={12} className="pipeline-spin" />
        <span>Analyzing data...</span>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="pipeline-badge error">
        <AlertTriangle size={12} />
        <span>{pipeline.error_msg || 'Pipeline error'}</span>
      </div>
    )
  }

  return null
}

// ─── Topic Card ───────────────────────────────────────────────

function TopicCard({
  topic,
  index,
  onPin,
  onRefresh,
  onClick,
  className = '',
  style,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
  className?: string
  style?: React.CSSProperties
}) {
  const alerts = (topic.summary_data?.alerts ?? []).map(normalizeAlert)
  const cardMetrics = topic.summary_data?.metrics ? extractCardMetrics(topic.summary_data.metrics) : []
  const d = index * 110

  return (
    <div
      className={`topic-card rise${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''} ${className}`}
      style={{ animationDelay: `${220 + d}ms`, ...style }}
      onDoubleClick={(e) => {
        if ((e.target as HTMLElement).closest('button')) return
        onClick(topic.id)
      }}
    >
      <div className="topic-card-shimmer" />

      {/* Header */}
      <div className="topic-card-header">
        <div className="topic-card-title-area">
          <div className="topic-card-icon-box">{topic.icon}</div>
          <div className="topic-card-title-info">
            <div className="topic-card-title-row">
              <h3 className="topic-card-name">{topic.name}</h3>
              <div className={`topic-status-pill ${topic.status === 'active' ? 'active' : 'paused'}`}>
                <span className="topic-status-dot">
                  <span className="topic-status-dot-inner" />
                  {topic.status === 'active' && <span className="topic-status-dot-ring" />}
                </span>
                {topic.status === 'active' ? 'Live' : 'Paused'}
              </div>
            </div>
            <p className="topic-card-updated">Updated {timeAgo(topic.last_crawl_at)}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
            onClick={() => onPin(topic.id, !topic.is_pinned)}
            title={topic.is_pinned ? 'Unpin' : 'Pin'}
          >
            <Pin size={13} />
          </button>
          <button className="topic-card-refresh" onClick={() => onRefresh(topic.id)}>
            <RefreshCw size={11} />
            Reanalyze
          </button>
        </div>
      </div>

      {/* Pipeline progress */}
      {topic.pipeline && <PipelineBadge pipeline={topic.pipeline} />}

      {/* Description */}
      {topic.last_summary ? (
        <p className="topic-card-summary">{stripMarkdown(topic.last_summary)}</p>
      ) : !topic.pipeline ? (
        <p className="topic-card-empty">Awaiting first analysis cycle...</p>
      ) : null}

      {/* Metrics tiles */}
      {cardMetrics.length > 0 && (
        <div className="topic-metrics-row">
          {cardMetrics.map((m, i) => (
            <div
              key={i}
              className="topic-metric-chip pop"
              style={{ animationDelay: `${340 + d + i * 70}ms` }}
            >
              <span className="topic-metric-label">{m.label}</span>
              <span
                className="topic-metric-value"
                style={m.color ? { color: m.color } : undefined}
              >
                {m.animate && typeof m.value === 'number' ? <AnimatedNum to={m.value} /> : m.value}
              </span>
              {m.sub && (
                <span
                  className="topic-metric-sub"
                  style={{
                    background: m.subBg,
                    border: `1px solid ${m.subColor}18`,
                    color: m.subColor,
                  }}
                >
                  {m.sub === 'bearish' ? '▼' : '▲'} {m.sub}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Alert */}
      {alerts.length > 0 && (
        <div className={`topic-card-alert ${alerts[0].level}`}>
          {alerts[0].level === 'critical' ? <AlertCircle size={13} /> : alerts[0].level === 'warning' ? <AlertTriangle size={13} /> : <Info size={13} />}
          <span>{alerts[0].message}</span>
          {alerts.length > 1 && <span className="topic-alert-more">+{alerts.length - 1}</span>}
        </div>
      )}

      {/* Footer */}
      <div className="topic-card-footer">
        <div className="topic-card-sources">
          <span className="topic-card-sources-label">Sources</span>
          {topic.platforms.map((p) => (
            <div key={p} className="topic-source-icon" title={p.toUpperCase()}>
              {p === 'x' ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              )}
            </div>
          ))}
        </div>
        <div className="topic-card-tags">
          {topic.keywords.slice(0, 3).map((kw) => (
            <span key={kw} className="topic-tag">#{kw}</span>
          ))}
          {topic.keywords.length > 3 && (
            <span className="topic-tag">+{topic.keywords.length - 3}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Zone Grid ────────────────────────────────────────────────

function ZoneGrid({
  zone,
  title,
  icon,
  items,
  activeId,
  hoverZone,
  crossingZone,
  cellRefs,
  onPointerDown,
  onPin,
  onRefresh,
  onClick,
  zoneRef,
}: {
  zone: Zone
  title: string
  icon: string
  items: Topic[]
  activeId: string | null
  hoverZone: Zone | null
  crossingZone: boolean
  cellRefs: React.MutableRefObject<Record<string, HTMLElement | null>>
  onPointerDown: (e: React.PointerEvent, id: string) => void
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
  zoneRef: React.RefObject<HTMLDivElement | null>
}) {
  const glowClass = crossingZone && hoverZone === zone
    ? zone === 'pin' ? 'zone-glow-pin' : 'zone-glow-unpin'
    : ''

  return (
    <div
      ref={zoneRef}
      className={`zone ${activeId ? 'zone-active' : ''} ${glowClass}`}
    >
      <div className="zone-hd">
        <span className="zone-icon">{icon}</span>
        <span className="zone-title">{title}</span>
        <span className="zone-ct">{items.length}</span>
        {crossingZone && hoverZone === zone && (
          <span className="zone-hint">
            {zone === 'pin' ? 'Drop to pin' : 'Drop to unpin'}
          </span>
        )}
      </div>

      {items.length === 0 && !activeId && zone === 'pin' && (
        <div className="zone-empty">Drag topics here to pin them</div>
      )}
      {items.length === 0 && activeId && zone === 'pin' && (
        <div className="zone-drop-target">
          <div className="zone-drop-inner">Drop here to pin</div>
        </div>
      )}

      <div className="zone-grid">
        {items.map((topic, i) => {
          const isDragging = topic.id === activeId
          return (
            <div
              key={topic.id}
              className="g-cell"
              ref={(el) => { cellRefs.current[topic.id] = el }}
              onPointerDown={(e) => {
                if ((e.target as HTMLElement).closest('button')) return
                onPointerDown(e, topic.id)
              }}
            >
              {isDragging && (
                <div className="drag-placeholder">
                  <div className="drag-placeholder-inner">
                    <div className="drag-placeholder-line w60" />
                    <div className="drag-placeholder-line w40" />
                    <div className="drag-placeholder-dots">
                      <div className="drag-placeholder-dot" />
                      <div className="drag-placeholder-dot" />
                      <div className="drag-placeholder-dot" />
                    </div>
                  </div>
                </div>
              )}
              <div style={{ opacity: isDragging ? 0 : 1, pointerEvents: isDragging ? 'none' : 'auto' }}>
                <TopicCard
                  topic={topic}
                  index={i}
                  onPin={onPin}
                  onRefresh={onRefresh}
                  onClick={onClick}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── SSE Helpers ─────────────────────────────────────────────

function extractReplyFromPartial(raw: string): string {
  const idx = raw.indexOf('"reply"')
  if (idx === -1) return ''
  const valStart = raw.indexOf('"', idx + 7)
  if (valStart === -1) return ''
  let result = ''
  let i = valStart + 1
  while (i < raw.length) {
    if (raw[i] === '\\' && i + 1 < raw.length) {
      const next = raw[i + 1]
      if (next === '"') result += '"'
      else if (next === 'n') result += '\n'
      else if (next === '\\') result += '\\'
      else result += next
      i += 2
    } else if (raw[i] === '"') {
      break
    } else {
      result += raw[i]
      i++
    }
  }
  return result
}

// ─── Create Topic Modal ───────────────────────────────────────

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

function CreateTopicModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('📊')
  const [description, setDescription] = useState('')
  const [platforms, setPlatforms] = useState<string[]>(['x'])
  const [keywords, setKeywords] = useState('')
  const [interval, setInterval] = useState('6')
  const [createTopic, { isLoading }] = useCreateTopicMutation()

  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([])
  const [streamingReply, setStreamingReply] = useState('')
  const [isAssisting, setIsAssisting] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, streamingReply])

  const resetForm = () => {
    setChatInput(''); setChatMessages([]); setStreamingReply(''); setIsAssisting(false)
    setName(''); setIcon('📊'); setDescription(''); setPlatforms(['x']); setKeywords(''); setInterval('6')
  }

  const emojiOptions = EMOJI_OPTIONS.includes(icon) ? EMOJI_OPTIONS : [icon, ...EMOJI_OPTIONS]

  const handleAsk = async () => {
    const q = chatInput.trim()
    if (!q || isAssisting) return
    const userMsg: ChatMsg = { role: 'user', content: q }
    const newMessages = [...chatMessages, userMsg]
    setChatMessages(newMessages)
    setChatInput('')
    setStreamingReply('')
    setIsAssisting(true)

    try {
      const res = await fetch('/api/topics/assist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: newMessages }),
      })
      if (!res.ok || !res.body) {
        setChatMessages([...newMessages, { role: 'assistant', content: 'Failed to connect to AI.' }])
        setIsAssisting(false)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let finalReply = ''

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
              const partial = extractReplyFromPartial(accumulated)
              if (partial) setStreamingReply(partial)
            } else if (evt.done) {
              finalReply = evt.reply || ''
              const s = evt.suggestion
              if (s) {
                if (s.name) setName(s.name)
                if (s.icon) setIcon(s.icon)
                if (s.description) setDescription(s.description)
                if (s.platforms?.length) setPlatforms(s.platforms)
                if (s.keywords?.length) setKeywords(s.keywords.join(', '))
                if (s.schedule_interval_hours) setInterval(String(s.schedule_interval_hours))
              }
            } else if (evt.error) {
              finalReply = `Error: ${evt.error}`
            }
          } catch { /* skip malformed SSE */ }
        }
      }
      setChatMessages([...newMessages, { role: 'assistant', content: finalReply || extractReplyFromPartial(accumulated) || accumulated }])
      setStreamingReply('')
    } catch {
      setChatMessages([...newMessages, { role: 'assistant', content: 'Connection error.' }])
    } finally {
      setIsAssisting(false)
    }
  }

  const handleSubmit = async () => {
    if (!name.trim() || platforms.length === 0) return
    let finalDesc = description.trim()
    if (chatMessages.length > 0) {
      const convo = chatMessages.map((m) => `${m.role === 'user' ? 'User' : 'AI'}: ${m.content}`).join('\n')
      finalDesc = finalDesc ? `${finalDesc}\n\n---\nAI Assist Log:\n${convo}` : `AI Assist Log:\n${convo}`
    }
    await createTopic({
      name: name.trim(),
      icon,
      description: finalDesc || undefined,
      platforms,
      keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean),
      config: { schedule_interval_hours: Number(interval) || 6 },
    })
    resetForm()
    onClose()
  }

  const togglePlatform = (p: string) => {
    setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])
  }

  return (
    <Modal open={open} onClose={onClose} title="New Topic" className="create-topic-panel">
      <div className="stack-sm">
        <div className="assist-section">
          <div className="assist-label"><Sparkles size={13} /> AI Assist</div>
          {(chatMessages.length > 0 || streamingReply) && (
            <div className="assist-messages">
              {chatMessages.map((m, i) => (
                <div key={i} className={`assist-msg ${m.role}`}>
                  <span className="assist-msg-text">{m.content}</span>
                </div>
              ))}
              {streamingReply && (
                <div className="assist-msg assistant">
                  <span className="assist-msg-text">{streamingReply}<span className="assist-cursor" /></span>
                </div>
              )}
              {isAssisting && !streamingReply && (
                <div className="assist-msg assistant">
                  <Loader2 size={13} className="assist-spinner" />
                  <span className="assist-msg-text">Thinking...</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
          <div className="assist-input-row">
            <input
              className="form-input assist-input"
              placeholder="Describe what you want to monitor..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAsk()}
              disabled={isAssisting}
            />
            <button className="assist-send" onClick={handleAsk} disabled={!chatInput.trim() || isAssisting}>
              {isAssisting ? <Loader2 size={14} className="assist-spinner" /> : <Send size={14} />}
            </button>
          </div>
        </div>
        <div className="assist-divider" />
        <div className="form-group">
          <label className="form-label">Icon</label>
          <div className="emoji-picker">
            {emojiOptions.map((e) => (
              <button key={e} className={`emoji-option${e === icon ? ' selected' : ''}`} onClick={() => setIcon(e)}>{e}</button>
            ))}
          </div>
        </div>
        <Input label="Name" placeholder="e.g. 马斯克" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="form-group">
          <label className="form-label">Description</label>
          <textarea className="form-input form-textarea" placeholder="Optional description..." value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="form-group">
          <label className="form-label">Platforms</label>
          <div className="flex gap-2">
            {PLATFORM_OPTIONS.map((p) => (
              <button
                key={p}
                className={`topic-tag${platforms.includes(p) ? ' platform' : ''}`}
                style={{ padding: '6px 14px', cursor: 'pointer' }}
                onClick={() => togglePlatform(p)}
              >{p.toUpperCase()}</button>
            ))}
          </div>
        </div>
        <Input label="Keywords (comma-separated)" placeholder="e.g. Elon Musk, SpaceX, Tesla" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <Input label="Refresh Interval (hours)" type="number" min={1} value={interval} onChange={(e) => setInterval(e.target.value)} />
        <button className="btn btn-primary" style={{ width: '100%', marginTop: 8 }} disabled={!name.trim() || platforms.length === 0 || isLoading} onClick={handleSubmit}>
          <Plus size={16} />
          {isLoading ? 'Creating...' : 'Create Topic'}
        </button>
      </div>
    </Modal>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────

export function DashboardPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState<'All' | 'Active' | 'Paused'>('All')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 600)
    return () => clearTimeout(t)
  }, [])

  // Poll faster when any topic has an active pipeline
  const [pollingInterval, setPollingInterval] = useState(30_000)
  const { data: topics, isLoading: topicsLoading } = useListTopicsQuery(undefined, { pollingInterval })

  useEffect(() => {
    const hasActivePipeline = topics?.some((t) => t.pipeline && t.pipeline.phase !== 'done')
    setPollingInterval(hasActivePipeline ? 3_000 : 30_000)
  }, [topics])

  const [updateTopic] = useUpdateTopicMutation()
  const [reanalyzeTopic] = useReanalyzeTopicMutation()
  const [reorderTopics] = useReorderTopicsMutation()

  const handleRefresh = useCallback((id: string) => { reanalyzeTopic(id) }, [reanalyzeTopic])
  const handleTopicClick = useCallback((id: string) => { navigate(`/topic/${id}`) }, [navigate])

  // Derive pinned / unpinned from topics + filter
  const allTopics = topics ?? []
  const filtered = filter === 'All' ? allTopics : filter === 'Active' ? allTopics.filter((t) => t.status === 'active') : allTopics.filter((t) => t.status === 'paused')
  const pinned = useMemo(() => filtered.filter((t) => t.is_pinned), [filtered])
  const unpinned = useMemo(() => filtered.filter((t) => !t.is_pinned), [filtered])

  // Refs for FLIP + stable flipSnap wrapper (ref breaks circular dep between useFlip ↔ useZoneDrag)
  const cellRefs = useRef<Record<string, HTMLElement | null>>({})
  const flipSnapRef = useRef<() => void>(() => {})
  const stableFlipSnap = useCallback(() => flipSnapRef.current(), [])

  // Drag-and-drop
  const handleDrop = useCallback((id: string, targetZone: Zone, insertIdx: number) => {
    const dragged = allTopics.find((t) => t.id === id)
    if (!dragged) return

    const pinnedList = pinned.filter((t) => t.id !== id).map((t) => t.id)
    const unpinnedList = unpinned.filter((t) => t.id !== id).map((t) => t.id)

    if (targetZone === 'pin') {
      pinnedList.splice(Math.min(insertIdx, pinnedList.length), 0, id)
    } else {
      unpinnedList.splice(Math.min(insertIdx, unpinnedList.length), 0, id)
    }

    reorderTopics({ pinned: pinnedList, unpinned: unpinnedList })
  }, [allTopics, pinned, unpinned, reorderTopics])

  const drag = useZoneDrag({
    pinnedIds: pinned.map((t) => t.id),
    unpinnedIds: unpinned.map((t) => t.id),
    cellRefs,
    flipSnap: stableFlipSnap,
    onDrop: handleDrop,
  })

  // Display lists with drag preview insertion
  const { displayPinned, displayUnpinned } = useMemo(() => {
    if (!drag.activeId || !drag.hoverZone) return { displayPinned: pinned, displayUnpinned: unpinned }
    const dragged = allTopics.find((t) => t.id === drag.activeId)
    if (!dragged) return { displayPinned: pinned, displayUnpinned: unpinned }

    const dp = pinned.filter((t) => t.id !== drag.activeId)
    const du = unpinned.filter((t) => t.id !== drag.activeId)
    const previewCard = { ...dragged, is_pinned: drag.hoverZone === 'pin' }
    const idx = drag.hoverIdx ?? 0

    if (drag.hoverZone === 'pin') {
      dp.splice(Math.min(idx, dp.length), 0, previewCard)
    } else {
      du.splice(Math.min(idx, du.length), 0, previewCard)
    }
    return { displayPinned: dp, displayUnpinned: du }
  }, [allTopics, pinned, unpinned, drag.activeId, drag.hoverZone, drag.hoverIdx])

  // FLIP animation — wire ref after hook so drag gets the real snapshot fn
  const flipKey = [...displayPinned, ...displayUnpinned].map((t) => t.id).join(',')
  const flipSnap = useFlip(flipKey, cellRefs, mounted)
  flipSnapRef.current = flipSnap

  // Derived drag state
  const activeTopic = drag.activeId ? allTopics.find((t) => t.id === drag.activeId) : null
  const dragSourceZone = activeTopic?.is_pinned ? 'pin' : 'unpin'
  const crossingZone = !!(drag.activeId && drag.hoverZone && drag.hoverZone !== dragSourceZone)

  // Pin via button (with FLIP)
  const handlePin = useCallback((id: string, pinned: boolean) => {
    flipSnapRef.current()
    updateTopic({ id, is_pinned: pinned })
  }, [updateTopic])

  const totalPosts = allTopics.reduce((s, t) => s + t.total_contents, 0)

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header rise">
        <div>
          <h1>Dashboard</h1>
          <p className="dashboard-subtitle">
            Tracking {allTopics.length} topics · {totalPosts} posts collected
          </p>
        </div>
        <button className="btn-accent" onClick={() => setShowCreate(true)}>
          <Plus size={15} />
          New Topic
        </button>
      </div>

      {/* Stats */}
      <div className="dashboard-stats rise" style={{ animationDelay: '80ms' }}>
        {[
          { label: 'Topics', value: allTopics.length, emoji: '📋' },
          { label: 'Active', value: allTopics.filter((t) => t.status === 'active').length, emoji: '🟢' },
        ].map((s, i) => (
          <div key={i} className="dash-stat pop" style={{ animationDelay: `${130 + i * 70}ms` }}>
            <span className="dash-stat-emoji">{s.emoji}</span>
            <div className="dash-stat-content">
              <span className="dash-stat-label">{s.label}</span>
              <span className="dash-stat-value">
                {typeof s.value === 'number' ? <AnimatedNum to={s.value} /> : s.value}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div className="dashboard-filter-bar rise" style={{ animationDelay: '180ms' }}>
        <span className="dashboard-topics-label">Topics</span>
        <div className="filter-pills">
          {(['All', 'Active', 'Paused'] as const).map((f) => (
            <button
              key={f}
              className={`filter-pill${filter === f ? ' filter-pill-active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Topic zones */}
      {topicsLoading ? (
        <div className="topic-grid">
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
          <div style={{ minHeight: 280 }}><Skeleton className="w-full h-full" /></div>
        </div>
      ) : (
        <>
          {/* Pinned Zone */}
          <ZoneGrid
            zone="pin"
            title="Pinned"
            icon="📌"
            items={displayPinned}
            activeId={drag.activeId}
            hoverZone={drag.hoverZone}
            crossingZone={crossingZone}
            cellRefs={cellRefs}
            onPointerDown={drag.handlePointerDown}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onClick={handleTopicClick}
            zoneRef={drag.pinZoneRef}
          />

          {/* All Topics Zone */}
          <ZoneGrid
            zone="unpin"
            title="All Topics"
            icon="📋"
            items={displayUnpinned}
            activeId={drag.activeId}
            hoverZone={drag.hoverZone}
            crossingZone={crossingZone}
            cellRefs={cellRefs}
            onPointerDown={drag.handlePointerDown}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onClick={handleTopicClick}
            zoneRef={drag.unpinZoneRef}
          />

          {/* Empty state */}
          {displayPinned.length === 0 && displayUnpinned.length === 0 && !drag.activeId && (
            <div className="topic-empty-state pop">
              <span style={{ fontSize: '2.5rem' }}>📊</span>
              <h3>No {filter.toLowerCase()} topics found</h3>
              <p>Create your first monitoring topic to get started</p>
              <button className="btn-accent" onClick={() => setShowCreate(true)}>
                <Plus size={15} />
                Create Topic
              </button>
            </div>
          )}
        </>
      )}

      {/* Drag Overlay */}
      {activeTopic && drag.activeRect && (
        <div
          className="drag-overlay"
          style={{
            left: drag.dragPos.x - drag.dragOffset.x,
            top: drag.dragPos.y - drag.dragOffset.y,
            width: drag.activeRect.w,
          }}
        >
          <TopicCard
            topic={{
              ...activeTopic,
              is_pinned: drag.hoverZone === 'pin' ? true : drag.hoverZone === 'unpin' ? false : activeTopic.is_pinned,
            }}
            index={0}
            onPin={() => {}}
            onRefresh={() => {}}
            onClick={() => {}}
            className={`drag-flying ${crossingZone ? 'cross-zone' : ''}`}
          />
          {crossingZone && (
            <div className="drag-badge">
              {drag.hoverZone === 'pin' ? '📌 Pin' : '📋 Unpin'}
            </div>
          )}
        </div>
      )}

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
