import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DndContext,
  DragOverlay,
  defaultDropAnimationSideEffects,
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
  Plus, Pin, RefreshCw, GripVertical,
  AlertTriangle,
  Sparkles, Send, Loader2, User,
  Pencil, X, Check, Link2,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Markdown } from '@/components/ui/Markdown'
import { useSSEChat } from '@/hooks/useSSEChat'
import {
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useReanalyzeTopicMutation,
  useReorderTopicsMutation,
  useListUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useReorderUsersMutation,
  useAttachUserMutation,
} from '@/store/api'
import type { Topic, TopicAlert, TopicPipeline, User as UserType, TopicStatus } from '@/types/models'

const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
const PLATFORM_OPTIONS = ['x', 'xhs']

/** uid() requires HTTPS; fallback for HTTP contexts */
const uid = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? uid()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`

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
  dragListeners,
  className = '',
  style,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
  dragListeners?: Record<string, unknown>
  className?: string
  style?: React.CSSProperties
}) {
  const alerts = (topic.summary_data?.alerts ?? []).map(normalizeAlert)
  const d = index * 80
  const [risen, setRisen] = useState(false)

  return (
    <div
      className={`topic-card${risen ? '' : ' rise'}${topic.is_pinned ? ' pinned' : ''}${topic.status === 'paused' ? ' paused' : ''} ${className}`}
      style={{ animationDelay: risen ? undefined : `${180 + d}ms`, ...style }}
      onAnimationEnd={(e) => { if (e.animationName === 'rise') setRisen(true) }}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button, .topic-drag-handle')) return
        onClick(topic.id)
      }}
    >
      <div className="topic-card-shimmer" />

      {/* Drag handle */}
      <div className="topic-drag-handle" {...dragListeners}>
        <GripVertical size={14} />
      </div>

      {/* Pin button — independent of actions so no flash on hover-out */}
      <button
        className={`topic-pin-btn${topic.is_pinned ? ' active' : ''}`}
        onClick={() => onPin(topic.id, !topic.is_pinned)}
        title={topic.is_pinned ? 'Unpin' : 'Pin'}
      >
        <Pin size={13} />
      </button>

      {/* Hover actions — float top-right */}
      <div className="topic-card-actions">
        <button className="topic-card-refresh" onClick={() => onRefresh(topic.id)}>
          <RefreshCw size={11} />
        </button>
      </div>

      {/* HEADER */}
      <div className="topic-card-row1">
        <div className="topic-card-icon-box">{topic.type === 'user' ? '👤' : topic.icon}</div>
        <h3 className="topic-card-name">{topic.name}</h3>
        {topic.type === 'user' && <span className="topic-tag platform" style={{ fontSize: '0.6rem', marginLeft: 4 }}>{topic.platforms[0]?.toUpperCase()}</span>}
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
          {topic.type === 'user' && topic.description ? (
            <span className="topic-tag">@{topic.description}</span>
          ) : (
            <>
              {topic.keywords.slice(0, 2).map((kw) => (
                <span key={kw} className="topic-tag">#{kw}</span>
              ))}
              {topic.keywords.length > 2 && (
                <span className="topic-tag-more">+{topic.keywords.length - 2}</span>
              )}
            </>
          )}
          {(topic.user_count ?? 0) > 0 && (
            <span className="topic-tag">{topic.user_count} users</span>
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
  onPin,
  onRefresh,
  onClick,
}: {
  topic: Topic
  index: number
  onPin: (id: string, pinned: boolean) => void
  onRefresh: (id: string) => void
  onClick: (id: string) => void
}) {
  const skipPostDrop: AnimateLayoutChanges = (args) =>
    args.active ? defaultAnimateLayoutChanges(args) : false

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: topic.id, animateLayoutChanges: skipPostDrop })

  // On the frame isDragging flips false → card becomes visible.
  // Force transform=0, transition=none so it appears at its DOM position
  // instantly, avoiding a flash from stale drag offsets.
  const wasDragging = useRef(false)
  const justDropped = wasDragging.current && !isDragging
  wasDragging.current = isDragging

  const style: React.CSSProperties = {
    transform: (isDragging || justDropped) ? 'translate3d(0, 0, 0)' : (transform ? CSS.Transform.toString(transform) : 'translate3d(0, 0, 0)'),
    transition: justDropped ? 'none' : transition,
    opacity: isDragging ? 0 : 1,
  }

  return (
    <div ref={setNodeRef} className="g-cell" style={style} {...attributes}>
      <TopicCard
        topic={topic}
        index={index}
        onPin={onPin}
        onRefresh={onRefresh}
        onClick={onClick}
        dragListeners={listeners}
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

// ─── Proposal Types ──────────────────────────────────────────

type ProposalType = 'create_topic' | 'create_user' | 'subscribe'

interface ProposalBase {
  _id: string
  type: ProposalType
  _status?: 'pending' | 'creating' | 'done' | 'error'
  _error?: string
}

interface CreateTopicProposal extends ProposalBase {
  type: 'create_topic'
  name: string
  icon: string
  description: string
  platforms: string[]
  keywords: string[]
  schedule_interval_hours: number
}

interface CreateUserProposal extends ProposalBase {
  type: 'create_user'
  name: string
  platform: string
  profile_url: string
  username: string
  schedule_interval_hours: number
}

interface SubscribeProposal extends ProposalBase {
  type: 'subscribe'
  user_ref: string
  topic_ref: string
}

type Proposal = CreateTopicProposal | CreateUserProposal | SubscribeProposal

function proposalSummary(p: Proposal): string {
  if (p.type === 'create_topic') {
    const kw = p.keywords.length > 0 ? `${p.keywords.length} kw` : ''
    return [p.platforms.map((x) => x.toUpperCase()).join(', '), kw, `${p.schedule_interval_hours}h`].filter(Boolean).join(' · ')
  }
  if (p.type === 'create_user') {
    return [p.platform.toUpperCase(), p.username ? `@${p.username}` : '', `${p.schedule_interval_hours}h`].filter(Boolean).join(' · ')
  }
  return `${p.user_ref} → ${p.topic_ref}`
}

function proposalIcon(p: Proposal): React.ReactNode {
  if (p.type === 'create_topic') return <Sparkles size={12} />
  if (p.type === 'create_user') return <User size={12} />
  return <Link2 size={12} />
}

function proposalLabel(p: Proposal): string {
  if (p.type === 'create_topic') return p.name || 'New Topic'
  if (p.type === 'create_user') return p.name || 'New User'
  return `Link ${p.user_ref} → ${p.topic_ref}`
}

// ─── Proposal Card ───────────────────────────────────────────

function ProposalCard({
  proposal: p,
  editing,
  onEdit,
  onDone,
  onChange,
  onRemove,
}: {
  proposal: Proposal
  editing: boolean
  onEdit: () => void
  onDone: () => void
  onChange: (updated: Proposal) => void
  onRemove: () => void
}) {
  const isSubmitting = p._status === 'creating'
  const isDone = p._status === 'done'
  const isError = p._status === 'error'

  if (!editing) {
    return (
      <div className={`proposal-card${isDone ? ' done' : ''}${isError ? ' error' : ''}`}>
        <span className="proposal-card-type">{proposalIcon(p)}</span>
        <div className="proposal-card-info">
          <span className="proposal-card-name">{proposalLabel(p)}</span>
          <span className="proposal-card-meta">{proposalSummary(p)}</span>
        </div>
        <div className="proposal-card-actions">
          {isSubmitting && <Loader2 size={12} className="assist-spinner" />}
          {isDone && <Check size={12} style={{ color: 'var(--positive)' }} />}
          {isError && <span className="proposal-card-error" title={p._error}>!</span>}
          {!isSubmitting && !isDone && (
            <>
              <button className="proposal-card-btn" onClick={onEdit} title="Edit"><Pencil size={12} /></button>
              <button className="proposal-card-btn" onClick={onRemove} title="Remove"><X size={12} /></button>
            </>
          )}
        </div>
      </div>
    )
  }

  // ── Edit Mode ──
  if (p.type === 'create_topic') {
    const tp = p as CreateTopicProposal
    const emojiOpts = EMOJI_OPTIONS.includes(tp.icon) ? EMOJI_OPTIONS : [tp.icon, ...EMOJI_OPTIONS]
    return (
      <div className="proposal-card editing">
        <div className="proposal-card-edit-header">
          <span className="proposal-card-type">{proposalIcon(p)}</span>
          <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>Edit Topic</span>
          <button className="proposal-card-btn" onClick={onDone} title="Done"><Check size={14} /></button>
        </div>
        <div className="proposal-card-edit-fields">
          <div className="form-group">
            <label className="form-label">Icon</label>
            <div className="emoji-picker">
              {emojiOpts.map((e) => (
                <button key={e} className={`emoji-option${e === tp.icon ? ' selected' : ''}`}
                  onClick={() => onChange({ ...tp, icon: e })}>{e}</button>
              ))}
            </div>
          </div>
          <div>
            <Input label="Name *" value={tp.name} onChange={(e) => onChange({ ...tp, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Platforms</label>
            <div className="platform-toggles">
              {PLATFORM_OPTIONS.map((pl) => (
                <button key={pl}
                  className={`platform-toggle${tp.platforms.includes(pl) ? ' active' : ''}`}
                  onClick={() => {
                    const next = tp.platforms.includes(pl)
                      ? tp.platforms.filter((x) => x !== pl)
                      : [...tp.platforms, pl]
                    if (next.length > 0) onChange({ ...tp, platforms: next })
                  }}
                >{pl.toUpperCase()}</button>
              ))}
            </div>
          </div>
          <div>
            <Input label="Keywords" value={tp.keywords.join(', ')}
              onChange={(e) => onChange({ ...tp, keywords: e.target.value.split(',').map((k) => k.trim()).filter(Boolean) })} />
          </div>
          <div className="create-topic-form-full">
            <Input label="Description" value={tp.description}
              onChange={(e) => onChange({ ...tp, description: e.target.value })} />
          </div>
          <div>
            <Input label="Interval (h)" type="number" min={1} value={String(tp.schedule_interval_hours)}
              onChange={(e) => onChange({ ...tp, schedule_interval_hours: Number(e.target.value) || 6 })} />
          </div>
        </div>
      </div>
    )
  }

  if (p.type === 'create_user') {
    const up = p as CreateUserProposal
    return (
      <div className="proposal-card editing">
        <div className="proposal-card-edit-header">
          <span className="proposal-card-type">{proposalIcon(p)}</span>
          <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>Edit User</span>
          <button className="proposal-card-btn" onClick={onDone} title="Done"><Check size={14} /></button>
        </div>
        <div className="proposal-card-edit-fields">
          <div>
            <Input label="Name *" value={up.name} onChange={(e) => onChange({ ...up, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Platform</label>
            <div className="platform-toggles">
              {PLATFORM_OPTIONS.map((pl) => (
                <button key={pl}
                  className={`platform-toggle${up.platform === pl ? ' active' : ''}`}
                  onClick={() => onChange({ ...up, platform: pl })}
                >{pl.toUpperCase()}</button>
              ))}
            </div>
          </div>
          <div className="create-topic-form-full">
            <Input label="Profile URL *" placeholder="https://x.com/username" value={up.profile_url}
              onChange={(e) => {
                const url = e.target.value
                const m = url.match(/(?:x\.com|twitter\.com)\/(@?\w+)/i)
                const username = m ? m[1].replace('@', '') : up.username
                onChange({ ...up, profile_url: url, username })
              }} />
          </div>
          <div>
            <Input label="Username" value={up.username}
              onChange={(e) => onChange({ ...up, username: e.target.value })} />
          </div>
          <div>
            <Input label="Interval (h)" type="number" min={1} value={String(up.schedule_interval_hours)}
              onChange={(e) => onChange({ ...up, schedule_interval_hours: Number(e.target.value) || 6 })} />
          </div>
        </div>
      </div>
    )
  }

  // subscribe
  const sp = p as SubscribeProposal
  return (
    <div className="proposal-card editing">
      <div className="proposal-card-edit-header">
        <span className="proposal-card-type">{proposalIcon(p)}</span>
        <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>Edit Link</span>
        <button className="proposal-card-btn" onClick={onDone} title="Done"><Check size={14} /></button>
      </div>
      <div className="proposal-card-edit-fields">
        <div>
          <Input label="User (name/username)" value={sp.user_ref}
            onChange={(e) => onChange({ ...sp, user_ref: e.target.value })} />
        </div>
        <div>
          <Input label="Topic name" value={sp.topic_ref}
            onChange={(e) => onChange({ ...sp, topic_ref: e.target.value })} />
        </div>
      </div>
    </div>
  )
}

// ─── Create Topic Modal ───────────────────────────────────────

function CreateTopicModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)

  const { data: allUsers } = useListUsersQuery()
  const { data: allTopics } = useListTopicsQuery()
  const [createTopic] = useCreateTopicMutation()
  const [createUser] = useCreateUserMutation()
  const [attachUser] = useAttachUserMutation()

  const buildBody = useCallback(
    (msgs: { role: string; content: string }[]) => ({ messages: msgs }),
    [],
  )

  const handleActions = useCallback((actions: Record<string, unknown>[]) => {
    const newProposals: Proposal[] = []
    for (const a of actions) {
      const _id = uid()
      if (a.type === 'create_topic') {
        newProposals.push({
          _id, type: 'create_topic',
          name: (a.name as string) || '',
          icon: (a.icon as string) || '📊',
          description: (a.description as string) || '',
          platforms: (a.platforms as string[]) || ['x'],
          keywords: (a.keywords as string[]) || [],
          schedule_interval_hours: (a.schedule_interval_hours as number) || 6,
        })
      } else if (a.type === 'create_user') {
        newProposals.push({
          _id, type: 'create_user',
          name: (a.name as string) || '',
          platform: (a.platform as string) || 'x',
          profile_url: (a.profile_url as string) || '',
          username: (a.username as string) || '',
          schedule_interval_hours: (a.schedule_interval_hours as number) || 6,
        })
      } else if (a.type === 'subscribe') {
        newProposals.push({
          _id, type: 'subscribe',
          user_ref: (a.user_ref as string) || '',
          topic_ref: (a.topic_ref as string) || '',
        })
      }
    }
    if (newProposals.length > 0) {
      setProposals((prev) => [...prev, ...newProposals])
    }
  }, [])

  const {
    messages: chatMessages, input: chatInput, setInput: setChatInput,
    streaming: isAssisting, streamingText: streamingReply,
    send: handleAsk, reset: resetChat, handleKeyDown, scrollRef: chatScrollRef,
  } = useSSEChat({
    endpoint: '/api/topics/assist',
    buildBody,
    mode: 'assist',
    onActions: handleActions,
  })

  const resetAll = useCallback(() => {
    resetChat()
    setProposals([])
    setEditingId(null)
    setManualOpen(false)
  }, [resetChat])

  const addManual = (type: 'topic' | 'user') => {
    const _id = uid()
    const p: Proposal = type === 'topic'
      ? { _id, type: 'create_topic', name: '', icon: '📊', description: '', platforms: ['x'], keywords: [], schedule_interval_hours: 6 }
      : { _id, type: 'create_user', name: '', platform: 'x', profile_url: '', username: '', schedule_interval_hours: 6 }
    setProposals((prev) => [...prev, p])
    setEditingId(_id)
    setManualOpen(false)
  }

  const handleSubmitAll = async () => {
    if (proposals.length === 0 || submitting) return
    setSubmitting(true)
    setEditingId(null)

    const createdTopics = new Map<string, string>()
    const createdUsers = new Map<string, string>()
    let failCount = 0

    // Helper to update a single proposal's status
    const setStatus = (id: string, status: Proposal['_status'], error?: string) => {
      if (status === 'error') failCount++
      setProposals((prev) => prev.map((p) => p._id === id ? { ...p, _status: status, _error: error } : p))
    }

    // 1. Create topics
    for (const p of proposals.filter((p) => p.type === 'create_topic')) {
      const tp = p as CreateTopicProposal
      if (!tp.name.trim()) { setStatus(tp._id, 'error', 'Name required'); continue }
      setStatus(tp._id, 'creating')
      try {
        const result = await createTopic({
          type: 'topic', name: tp.name.trim(), icon: tp.icon,
          description: tp.description || undefined,
          platforms: tp.platforms,
          keywords: tp.keywords,
          config: { schedule_interval_hours: tp.schedule_interval_hours },
        }).unwrap()
        createdTopics.set(tp.name.trim(), result.id)
        setStatus(tp._id, 'done')
      } catch (e) {
        setStatus(tp._id, 'error', String(e))
      }
    }

    // 2. Create users
    for (const p of proposals.filter((p) => p.type === 'create_user')) {
      const up = p as CreateUserProposal
      if (!up.name.trim() || !up.profile_url.trim()) { setStatus(up._id, 'error', 'Name & URL required'); continue }
      setStatus(up._id, 'creating')
      try {
        const result = await createUser({
          name: up.name.trim(), platform: up.platform,
          profile_url: up.profile_url.trim(),
          username: up.username || undefined,
          config: { schedule_interval_hours: up.schedule_interval_hours },
        }).unwrap()
        createdUsers.set(up.name.trim(), result.id)
        if (up.username) createdUsers.set(up.username, result.id)
        setStatus(up._id, 'done')
      } catch (e) {
        setStatus(up._id, 'error', String(e))
      }
    }

    // 3. Process subscriptions
    for (const p of proposals.filter((p) => p.type === 'subscribe')) {
      const sp = p as SubscribeProposal
      setStatus(sp._id, 'creating')
      const userId = createdUsers.get(sp.user_ref)
        || allUsers?.find((u) => u.name === sp.user_ref || u.username === sp.user_ref)?.id
      const topicId = createdTopics.get(sp.topic_ref)
        || allTopics?.find((t) => t.name === sp.topic_ref)?.id
      if (userId && topicId) {
        try {
          await attachUser({ userId, topicId })
          setStatus(sp._id, 'done')
        } catch (e) {
          setStatus(sp._id, 'error', String(e))
        }
      } else {
        setStatus(sp._id, 'error', `Could not resolve: ${!userId ? sp.user_ref : sp.topic_ref}`)
      }
    }

    setSubmitting(false)

    // If all succeeded, close after a brief delay
    if (failCount === 0) {
      setTimeout(() => { resetAll(); onClose() }, 600)
    }
  }

  // Count pending (not yet submitted) proposals
  const pendingCount = proposals.filter((p) => !p._status || p._status === 'pending' || p._status === 'error').length

  return (
    <Modal open={open} onClose={() => { resetAll(); onClose() }} title="Create" className="create-topic-panel">
      <div className="create-topic-content">
        {/* ── Chat Area ── */}
        <div className="create-topic-chat">
          <div className="create-topic-chat-messages">
            {chatMessages.length === 0 && !streamingReply && !isAssisting ? (
              <div className="create-topic-chat-empty">
                <Sparkles size={24} />
                <p>Tell AI what you want to monitor or follow,</p>
                <p>or add manually below.</p>
              </div>
            ) : (
              <>
                {chatMessages.map((m, i) => (
                  <div key={i} className={`topic-chat-msg ${m.role}`}>
                    <div className="topic-chat-msg-content">
                      {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
                    </div>
                  </div>
                ))}
                {streamingReply && (
                  <div className="topic-chat-msg assistant">
                    <div className="topic-chat-msg-content">
                      <Markdown>{streamingReply}</Markdown>
                      <span className="assist-cursor" />
                    </div>
                  </div>
                )}
                {isAssisting && !streamingReply && (
                  <div className="topic-chat-msg assistant">
                    <div className="topic-chat-msg-content">
                      <Loader2 size={13} className="assist-spinner" />
                      Thinking...
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={chatScrollRef} />
          </div>
          <div className="create-topic-chat-input-row">
            <textarea
              className="topic-chat-input"
              placeholder="Describe what you want to monitor or follow..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isAssisting}
              rows={1}
            />
            <button className="assist-send" onClick={handleAsk} disabled={!chatInput.trim() || isAssisting}>
              {isAssisting ? <Loader2 size={14} className="assist-spinner" /> : <Send size={14} />}
            </button>
          </div>
        </div>

        {/* ── Proposal List ── */}
        <div className="proposal-list">
          {proposals.length > 0 && (
            <div className="proposal-list-header">
              <span>Pending Actions ({proposals.length})</span>
            </div>
          )}
          <div className="proposal-list-cards">
            {proposals.map((p) => (
              <ProposalCard
                key={p._id}
                proposal={p}
                editing={editingId === p._id}
                onEdit={() => setEditingId(p._id)}
                onDone={() => setEditingId(null)}
                onChange={(updated) => setProposals((prev) => prev.map((x) => x._id === p._id ? updated : x))}
                onRemove={() => { setProposals((prev) => prev.filter((x) => x._id !== p._id)); if (editingId === p._id) setEditingId(null) }}
              />
            ))}
          </div>

          {/* Manual add (collapsed by default) */}
          {!submitting && (
            <div className="proposal-manual">
              {manualOpen ? (
                <div className="proposal-manual-buttons">
                  <button className="proposal-manual-btn" onClick={() => addManual('topic')}>
                    <Sparkles size={12} /> + Topic
                  </button>
                  <button className="proposal-manual-btn" onClick={() => addManual('user')}>
                    <User size={12} /> + User
                  </button>
                </div>
              ) : (
                <button className="proposal-manual-toggle" onClick={() => setManualOpen(true)}>
                  or add manually ▸
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Submit All ── */}
      <button
        className="btn btn-create"
        disabled={pendingCount === 0 || submitting}
        onClick={handleSubmitAll}
      >
        {submitting ? <Loader2 size={18} className="assist-spinner" /> : <Plus size={18} />}
        <span className="btn-create-label">
          {submitting ? 'Creating...' : `Submit All (${pendingCount})`}
        </span>
      </button>
    </Modal>
  )
}

// ─── Dashboard Page ───────────────────────────────────────────

export function DashboardPage() {
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState<'All' | 'Active' | 'Paused'>('All')

  // Sliding indicator for filter pills
  const pillsRef = useRef<HTMLDivElement>(null)
  const [slider, setSlider] = useState({ left: 0, width: 0, ready: false })
  useEffect(() => {
    if (!pillsRef.current) return
    const btn = pillsRef.current.querySelector('.filter-pill-active') as HTMLElement | null
    if (btn) setSlider({ left: btn.offsetLeft, width: btn.offsetWidth, ready: true })
  }, [filter])

  // Poll faster when any entity has an active pipeline
  const [pollingInterval, setPollingInterval] = useState(30_000)
  const { data: topics, isLoading: topicsLoading } = useListTopicsQuery(undefined, { pollingInterval })
  const { data: standaloneUsers, isLoading: usersLoading } = useListUsersQuery({ standalone: true }, { pollingInterval })

  useEffect(() => {
    const hasActivePipeline = topics?.some((t) => t.pipeline && t.pipeline.phase !== 'done')
      || standaloneUsers?.some((u) => u.pipeline && u.pipeline.phase !== 'done')
    setPollingInterval(hasActivePipeline ? 3_000 : 30_000)
  }, [topics, standaloneUsers])

  const [updateTopic] = useUpdateTopicMutation()
  const [updateUser] = useUpdateUserMutation()
  const [reanalyzeTopic] = useReanalyzeTopicMutation()
  const [reorderTopics] = useReorderTopicsMutation()
  const [reorderUsers] = useReorderUsersMutation()

  const handleRefresh = useCallback((id: string) => { reanalyzeTopic(id) }, [reanalyzeTopic])
  const handleTopicClick = useCallback((id: string) => {
    // Check if it's a user card (type === 'user') by looking up in allTopics
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (item?.type === 'user') navigate(`/user/${id}`)
    else navigate(`/topic/${id}`)
  }, [navigate])

  // Map standalone users to Topic-like objects for the shared grid
  const userAsTopic = useCallback((u: UserType): Topic => ({
    id: u.id,
    type: 'user',
    name: u.name,
    icon: '👤',
    description: u.username, // store username in description for card display
    platforms: [u.platform],
    keywords: [],
    config: u.config,
    status: u.status as TopicStatus,
    is_pinned: u.is_pinned,
    position: u.position,
    total_contents: u.total_contents,
    last_crawl_at: u.last_crawl_at,
    last_summary: u.last_summary,
    summary_data: u.summary_data,
    pipeline: u.pipeline,
    created_at: u.created_at,
    updated_at: u.updated_at,
  }), [])

  // Merge topics + standalone users
  const allTopics = useMemo(() => {
    const t = topics ?? []
    const u = (standaloneUsers ?? []).map(userAsTopic)
    return [...t, ...u]
  }, [topics, standaloneUsers, userAsTopic])
  const allTopicsRef = useRef(allTopics)
  allTopicsRef.current = allTopics
  const filtered = filter === 'All' ? allTopics : filter === 'Active' ? allTopics.filter((t) => t.status === 'active') : allTopics.filter((t) => t.status === 'paused')
  const pinned = useMemo(() => filtered.filter((t) => t.is_pinned), [filtered])
  const unpinned = useMemo(() => filtered.filter((t) => !t.is_pinned), [filtered])

  // ── DnD local state ──
  const [activeId, setActiveId] = useState<string | null>(null)
  const [containers, setContainers] = useState<{ pinned: string[]; unpinned: string[] }>({ pinned: [], unpinned: [] })
  const containersRef = useRef(containers)
  containersRef.current = containers
  const skipSyncRef = useRef(false)

  // Sync from server when not dragging (skip one cycle after drop
  // so the local reorder isn't overwritten by stale server data)
  const pinnedKey = useMemo(() => pinned.map((t) => t.id).join(','), [pinned])
  const unpinnedKey = useMemo(() => unpinned.map((t) => t.id).join(','), [unpinned])

  useEffect(() => {
    if (activeId) return
    if (skipSyncRef.current) { skipSyncRef.current = false; return }
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
    if (!over || over.id === active.id) return

    const activeContainer = findContainer(active.id as string)
    let overContainer = findContainer(over.id as string)
    if (!overContainer) {
      if (over.id === 'zone-pinned') overContainer = 'pinned'
      else if (over.id === 'zone-unpinned') overContainer = 'unpinned'
    }

    if (!activeContainer || !overContainer) return

    if (activeContainer === overContainer) {
      // Same-container: reorder DOM in real-time so drop has no flash
      setContainers((prev) => {
        const items = [...prev[activeContainer]]
        const oldIndex = items.indexOf(active.id as string)
        const newIndex = items.indexOf(over.id as string)
        if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return prev
        return { ...prev, [activeContainer]: arrayMove(items, oldIndex, newIndex) }
      })
    } else {
      // Cross-container: move item between zones
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
    }
  }, [findContainer])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { over } = event

    if (!over) {
      setActiveId(null)
      setContainers({
        pinned: pinnedKey ? pinnedKey.split(',') : [],
        unpinned: unpinnedKey ? unpinnedKey.split(',') : [],
      })
      return
    }

    // DOM order already matches visual order (updated in handleDragOver),
    // just finalize: clear active and persist to backend.
    // Skip the next sync so stale server data doesn't overwrite our local order.
    skipSyncRef.current = true
    setActiveId(null)

    // Split IDs by type — topics and users have separate reorder APIs
    const isUserItem = (id: string) => allTopicsRef.current.find(t => t.id === id)?.type === 'user'
    const { pinned, unpinned } = containersRef.current
    const topicPinned = pinned.filter(id => !isUserItem(id))
    const topicUnpinned = unpinned.filter(id => !isUserItem(id))
    const userPinned = pinned.filter(id => isUserItem(id))
    const userUnpinned = unpinned.filter(id => isUserItem(id))

    if (topicPinned.length > 0 || topicUnpinned.length > 0) {
      reorderTopics({ pinned: topicPinned, unpinned: topicUnpinned })
    }
    if (userPinned.length > 0 || userUnpinned.length > 0) {
      reorderUsers({ pinned: userPinned, unpinned: userUnpinned })
    }
  }, [reorderTopics, reorderUsers, pinnedKey, unpinnedKey])

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

  // Pin via button — route to correct mutation based on type
  const handlePin = useCallback((id: string, pinned: boolean) => {
    const item = allTopicsRef.current.find((t) => t.id === id)
    if (item?.type === 'user') updateUser({ id, is_pinned: pinned })
    else updateTopic({ id, is_pinned: pinned })
  }, [updateTopic, updateUser])

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
          New
        </button>
      </div>

      {/* Filter bar */}
      <div className="dashboard-filter-bar rise" style={{ animationDelay: '100ms' }}>
        <div className="filter-pills" ref={pillsRef}>
          <div
            className="filter-pill-slider"
            style={{ left: slider.left, width: slider.width, opacity: slider.ready ? 1 : 0 }}
          />
          {([
            { key: 'All' as const, count: allTopics.length },
            { key: 'Active' as const, count: allTopics.filter(t => t.status === 'active').length },
            { key: 'Paused' as const, count: allTopics.filter(t => t.status !== 'active').length },
          ]).map((f) => (
            <button
              key={f.key}
              className={`filter-pill${filter === f.key ? ' filter-pill-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.key}
              <span className="filter-pill-count">{f.count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Topic zones */}
      {(topicsLoading || usersLoading) ? (
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
            onPin={handlePin}
            onRefresh={handleRefresh}
            onClick={handleTopicClick}
          />

          {/* Empty state */}
          {displayPinned.length === 0 && displayUnpinned.length === 0 && !activeId && (
            <div className="topic-empty-state pop">
              <span style={{ fontSize: '2.5rem' }}>📊</span>
              <h3>No {filter.toLowerCase()} topics found</h3>
              <p>Create your first topic or user to get started</p>
              <button className="btn-accent" onClick={() => setShowCreate(true)}>
                <Plus size={15} />
                Create
              </button>
            </div>
          )}

          <DragOverlay dropAnimation={{
            duration: 180,
            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
            sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0' } } }),
          }}>
            {activeTopic && (
              <TopicCard
                topic={{ ...activeTopic, is_pinned: currentDragZone === 'pinned' }}
                index={0}
                onPin={() => {}}
                onRefresh={() => {}}
                onClick={() => {}}
                className={`drag-flying ${crossingZone ? 'cross-zone' : ''}`}
              />
            )}
          </DragOverlay>
        </DndContext>
      )}

      {/* FAB: mobile-only "New Topic" button */}
      <button className="fab" onClick={() => setShowCreate(true)} aria-label="New Topic">
        <Plus size={24} />
      </button>

      <CreateTopicModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
