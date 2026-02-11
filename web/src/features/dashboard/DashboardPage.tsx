import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
  useDroppable,
  type DragStartEvent,
  type DragOverEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  arrayMove,
  rectSortingStrategy,
  defaultAnimateLayoutChanges,
  type AnimateLayoutChanges,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Plus, Pin, RefreshCw,
  AlertTriangle,
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

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

// ─── Custom Sensor (ignores buttons) ────────────────────────

class SmartPointerSensor extends PointerSensor {
  static activators = [
    {
      eventName: 'onPointerDown' as const,
      handler: ({ nativeEvent: e }: { nativeEvent: PointerEvent }) => {
        return e.button === 0 && !(e.target as HTMLElement).closest('button, [data-no-dnd]')
      },
    },
  ]
}

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
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}m`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
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
  const d = index * 80

  return (
    <div
      className={`topic-card rise${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''} ${className}`}
      style={{ animationDelay: `${180 + d}ms`, ...style }}
      onDoubleClick={(e) => {
        if ((e.target as HTMLElement).closest('button')) return
        onClick(topic.id)
      }}
    >
      <div className="topic-card-shimmer" />

      {/* Hover actions — float top-right */}
      <div className="topic-card-actions">
        <button
          className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
          onClick={() => onPin(topic.id, !topic.is_pinned)}
          title={topic.is_pinned ? 'Unpin' : 'Pin'}
        >
          <Pin size={13} />
        </button>
        <button className="topic-card-refresh" onClick={() => onRefresh(topic.id)}>
          <RefreshCw size={11} />
        </button>
      </div>

      {/* HEADER */}
      <div className="topic-card-row1">
        <div className="topic-card-icon-box">{topic.icon}</div>
        <h3 className="topic-card-name">{topic.name}</h3>
        <span className={`topic-status-pill ${topic.status}`}>
          <span className="topic-status-pill-dot" />
          {topic.status === 'active' ? 'Live' : 'Paused'}
        </span>
      </div>

      <div className="topic-card-subtitle">
        {timeAgo(topic.last_crawl_at)}
        <span className="meta-sep">&middot;</span>
        {fmtNum(topic.total_contents)} posts
      </div>

      {/* Pipeline progress */}
      {topic.pipeline && <PipelineBadge pipeline={topic.pipeline} />}

      {/* MIDDLE — description + future per-topic widget slot */}
      <div className="topic-card-middle">
        {alerts.length > 0 ? (
          <p className="topic-card-summary">
            <span className="topic-card-alert-icon">
              {alerts[0].level === 'critical' ? '🔴' : alerts[0].level === 'warning' ? '⚠️' : 'ℹ️'}
            </span>
            {topic.last_summary ? stripMarkdown(topic.last_summary) : alerts[0].message}
          </p>
        ) : topic.last_summary ? (
          <p className="topic-card-summary">{stripMarkdown(topic.last_summary)}</p>
        ) : !topic.pipeline ? (
          <p className="topic-card-empty">Awaiting first analysis cycle...</p>
        ) : null}
      </div>

      {/* FOOTER */}
      <div className="topic-card-footer">
        <div className="topic-card-sources">
          {topic.platforms.map((p) => (
            <span key={p} className="topic-source-icon" title={p.toUpperCase()}>
              {p === 'x' ? (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              )}
            </span>
          ))}
        </div>
        <div className="topic-card-tags">
          {topic.keywords.slice(0, 2).map((kw) => (
            <span key={kw} className="topic-tag">#{kw}</span>
          ))}
          {topic.keywords.length > 2 && (
            <span className="topic-tag-more">+{topic.keywords.length - 2}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Sortable Card Wrapper ──────────────────────────────────

function SortableCard({
  topic,
  index,
  cellRefs,
  onPin,
  onRefresh,
  onClick,
}: {
  topic: Topic
  index: number
  cellRefs: React.MutableRefObject<Record<string, HTMLElement | null>>
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
}) {
  const noDropTransition: AnimateLayoutChanges = (args) =>
    args.wasDragging ? false : defaultAnimateLayoutChanges(args)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: topic.id, animateLayoutChanges: noDropTransition })

  const ref = useCallback((el: HTMLElement | null) => {
    setNodeRef(el)
    cellRefs.current[topic.id] = el
  }, [setNodeRef, topic.id, cellRefs])

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0 : 1,
  }

  return (
    <div ref={ref} className="g-cell" style={style} {...attributes} {...listeners}>
      <TopicCard
        topic={topic}
        index={index}
        onPin={onPin}
        onRefresh={onRefresh}
        onClick={onClick}
      />
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
  crossingZone,
  currentDragZone,
  cellRefs,
  onPin,
  onRefresh,
  onClick,
}: {
  zone: 'pinned' | 'unpinned'
  title: string
  icon: string
  items: Topic[]
  activeId: string | null
  crossingZone: boolean
  currentDragZone: string | null
  cellRefs: React.MutableRefObject<Record<string, HTMLElement | null>>
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
}) {
  const { setNodeRef } = useDroppable({ id: `zone-${zone}` })

  const glowClass = crossingZone && currentDragZone === zone
    ? zone === 'pinned' ? 'zone-glow-pin' : 'zone-glow-unpin'
    : ''

  return (
    <div
      ref={setNodeRef}
      className={`zone ${activeId ? 'zone-active' : ''} ${glowClass}`}
    >
      <div className="zone-hd">
        <span className="zone-icon">{icon}</span>
        <span className="zone-title">{title}</span>
        <span className="zone-ct">{items.length}</span>
        {crossingZone && currentDragZone === zone && (
          <span className="zone-hint">
            {zone === 'pinned' ? 'Drop to pin' : 'Drop to unpin'}
          </span>
        )}
      </div>

      {items.length === 0 && !activeId && zone === 'pinned' && (
        <div className="zone-empty">Drag topics here to pin them</div>
      )}
      {items.length === 0 && activeId && zone === 'pinned' && (
        <div className="zone-drop-target">
          <div className="zone-drop-inner">Drop here to pin</div>
        </div>
      )}

      <SortableContext items={items.map((t) => t.id)} strategy={rectSortingStrategy}>
        <div className="zone-grid">
          {items.map((topic, i) => (
            <SortableCard
              key={topic.id}
              topic={topic}
              index={i}
              cellRefs={cellRefs}
              onPin={onPin}
              onRefresh={onRefresh}
              onClick={onClick}
            />
          ))}
        </div>
      </SortableContext>
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

  // ── DnD local state ──
  const [activeId, setActiveId] = useState<string | null>(null)
  const [containers, setContainers] = useState<{ pinned: string[]; unpinned: string[] }>({ pinned: [], unpinned: [] })
  const containersRef = useRef(containers)
  containersRef.current = containers

  // Sync from server when not dragging
  const pinnedKey = useMemo(() => pinned.map((t) => t.id).join(','), [pinned])
  const unpinnedKey = useMemo(() => unpinned.map((t) => t.id).join(','), [unpinned])

  useEffect(() => {
    if (activeId) return
    setContainers({
      pinned: pinnedKey ? pinnedKey.split(',') : [],
      unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
    })
  }, [pinnedKey, unpinnedKey, activeId])

  // Build display lists from local container state
  const topicMap = useMemo(() => {
    const map = new Map<string, Topic>()
    allTopics.forEach((t) => map.set(t.id, t))
    return map
  }, [allTopics])

  const displayPinned = useMemo(
    () => containers.pinned.map((id) => topicMap.get(id)).filter((t): t is Topic => !!t),
    [containers.pinned, topicMap],
  )
  const displayUnpinned = useMemo(
    () => containers.unpinned.map((id) => topicMap.get(id)).filter((t): t is Topic => !!t),
    [containers.unpinned, topicMap],
  )

  // Ref map for measuring overlay width on drag start
  const cellRefs = useRef<Record<string, HTMLElement | null>>({})

  // DnD sensors
  const sensors = useSensors(
    useSensor(SmartPointerSensor, { activationConstraint: { distance: 8 } }),
  )

  const findContainer = useCallback((id: string): 'pinned' | 'unpinned' | null => {
    if (containersRef.current.pinned.includes(id)) return 'pinned'
    if (containersRef.current.unpinned.includes(id)) return 'unpinned'
    return null
  }, [])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }, [])

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event
    if (!over) return

    const activeContainer = findContainer(active.id as string)
    let overContainer = findContainer(over.id as string)
    if (!overContainer) {
      if (over.id === 'zone-pinned') overContainer = 'pinned'
      else if (over.id === 'zone-unpinned') overContainer = 'unpinned'
    }

    if (!activeContainer || !overContainer || activeContainer === overContainer) return

    // Cross-container move only — same-container reorder is handled visually
    // by useSortable transforms, then committed in onDragEnd
    setContainers((prev) => {
      const from = [...prev[activeContainer]]
      const to = [...prev[overContainer!]]

      const activeIndex = from.indexOf(active.id as string)
      if (activeIndex === -1) return prev
      from.splice(activeIndex, 1)

      const overIndex = to.indexOf(over.id as string)
      to.splice(overIndex >= 0 ? overIndex : to.length, 0, active.id as string)

      return { ...prev, [activeContainer]: from, [overContainer!]: to }
    })
  }, [findContainer])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event

    if (!over) {
      setActiveId(null)
      setContainers({
        pinned: pinnedKey ? pinnedKey.split(',') : [],
        unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
      })
      return
    }

    // For same-container reorders, commit the arrayMove now
    const activeContainer = findContainer(active.id as string)
    let overContainer = findContainer(over.id as string)
    if (!overContainer) {
      if (over.id === 'zone-pinned') overContainer = 'pinned'
      else if (over.id === 'zone-unpinned') overContainer = 'unpinned'
    }

    let finalContainers = containersRef.current
    if (activeContainer && overContainer && activeContainer === overContainer) {
      const items = [...containersRef.current[activeContainer]]
      const oldIndex = items.indexOf(active.id as string)
      const newIndex = items.indexOf(over.id as string)
      if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
        finalContainers = { ...containersRef.current, [activeContainer]: arrayMove(items, oldIndex, newIndex) }
        setContainers(finalContainers)
      }
    }

    setActiveId(null)
    reorderTopics({ pinned: finalContainers.pinned, unpinned: finalContainers.unpinned })
  }, [findContainer, reorderTopics, pinnedKey, unpinnedKey])

  const handleDragCancel = useCallback(() => {
    setActiveId(null)
    setContainers({
      pinned: pinnedKey ? pinnedKey.split(',') : [],
      unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
    })
  }, [pinnedKey, unpinnedKey])

  // Derived drag state for visual effects
  const activeTopic = activeId ? topicMap.get(activeId) ?? null : null
  const originalZone = activeTopic?.is_pinned ? 'pinned' : 'unpinned'
  const currentDragZone = activeId ? findContainer(activeId) : null
  const crossingZone = !!(activeId && currentDragZone && currentDragZone !== originalZone)

  // Pin via button
  const handlePin = useCallback((id: string, pinned: boolean) => {
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
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          {/* Pinned Zone */}
          <ZoneGrid
            zone="pinned"
            title="Pinned"
            icon="📌"
            items={displayPinned}
            activeId={activeId}
            crossingZone={crossingZone}
            currentDragZone={currentDragZone}
            cellRefs={cellRefs}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onClick={handleTopicClick}
          />

          {/* All Topics Zone */}
          <ZoneGrid
            zone="unpinned"
            title="All Topics"
            icon="📋"
            items={displayUnpinned}
            activeId={activeId}
            crossingZone={crossingZone}
            currentDragZone={currentDragZone}
            cellRefs={cellRefs}
            onPin={handlePin}
            onRefresh={handleRefresh}
            onClick={handleTopicClick}
          />

          {/* Empty state */}
          {displayPinned.length === 0 && displayUnpinned.length === 0 && !activeId && (
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

          <DragOverlay dropAnimation={null}>
            {activeTopic && (
              <div style={{ width: cellRefs.current[activeId!]?.offsetWidth }}>
                <TopicCard
                  topic={{
                    ...activeTopic,
                    is_pinned: currentDragZone === 'pinned',
                  }}
                  index={0}
                  onPin={() => {}}
                  onRefresh={() => {}}
                  onClick={() => {}}
                  className={`drag-flying ${crossingZone ? 'cross-zone' : ''}`}
                />
                {crossingZone && (
                  <div className="drag-badge">
                    {currentDragZone === 'pinned' ? '📌 Pin' : '📋 Unpin'}
                  </div>
                )}
              </div>
            )}
          </DragOverlay>
        </DndContext>
      )}

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
