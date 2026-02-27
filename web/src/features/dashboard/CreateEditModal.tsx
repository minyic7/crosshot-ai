import { useState, useEffect, useCallback } from 'react'
import {
  Sparkles, Send, Loader2, User,
  Pencil, X, Check, Link2, Plus,
} from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Markdown } from '@/components/ui/Markdown'
import { useSSEChat } from '@/hooks/useSSEChat'
import {
  useListTopicsQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useListUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useAttachUserMutation,
} from '@/store/api'
import type { Topic, User as UserType } from '@/types/models'

// ─── Constants ────────────────────────────────────────────────

export const EMOJI_OPTIONS = ['📊', '🔍', '🚀', '💡', '🔥', '📈', '🎯', '🌐', '💰', '⚡', '🤖', '📱']
export const PLATFORM_OPTIONS = ['x', 'xhs', 'web']

/** uid() requires HTTPS; fallback for HTTP contexts */
const uid = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`

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

// ─── Proposal Helpers ────────────────────────────────────────

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

function proposalLabel(p: Proposal, editMode: boolean): string {
  if (p.type === 'create_topic') return p.name || (editMode ? 'Edit Topic' : 'New Topic')
  if (p.type === 'create_user') return p.name || (editMode ? 'Edit User' : 'New User')
  return `Link ${p.user_ref} → ${p.topic_ref}`
}

// ─── Proposal Card ───────────────────────────────────────────

function ProposalCard({
  proposal: p,
  editing,
  editMode,
  onEdit,
  onDone,
  onChange,
  onRemove,
  proposals,
  allTopics,
  allUsers,
}: {
  proposal: Proposal
  editing: boolean
  editMode: boolean
  onEdit: () => void
  onDone: () => void
  onChange: (updated: Proposal) => void
  onRemove: () => void
  proposals: Proposal[]
  allTopics: { id: string; name: string; icon?: string }[] | undefined
  allUsers: { id: string; name: string; username?: string | null }[] | undefined
}) {
  const isSubmitting = p._status === 'creating'
  const isDone = p._status === 'done'
  const isError = p._status === 'error'

  if (!editing) {
    return (
      <div className={`proposal-card${isDone ? ' done' : ''}${isError ? ' error' : ''}`}>
        <span className="proposal-card-type">{proposalIcon(p)}</span>
        <div className="proposal-card-info">
          <span className="proposal-card-name">{proposalLabel(p, editMode)}</span>
          <span className="proposal-card-meta">{proposalSummary(p)}</span>
        </div>
        <div className="proposal-card-actions">
          {isSubmitting && <Loader2 size={12} className="assist-spinner" />}
          {isDone && <Check size={12} style={{ color: 'var(--positive)' }} />}
          {isError && <span className="proposal-card-error" title={p._error}>!</span>}
          {!isSubmitting && !isDone && (
            <>
              <button className="proposal-card-btn" onClick={onEdit} title="Edit"><Pencil size={12} /></button>
              {!editMode && <button className="proposal-card-btn" onClick={onRemove} title="Remove"><X size={12} /></button>}
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
          <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>{editMode ? 'Edit Topic' : 'New Topic'}</span>
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
          <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>{editMode ? 'Edit User' : 'New User'}</span>
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

  // subscribe — dropdown selectors
  const sp = p as SubscribeProposal

  const userOptions: { value: string; label: string }[] = []
  for (const pr of proposals) {
    if (pr.type === 'create_user' && pr.name.trim()) {
      userOptions.push({ value: pr.name.trim(), label: `${pr.name.trim()} (new)` })
    }
  }
  for (const u of allUsers ?? []) {
    userOptions.push({ value: u.username || u.name, label: u.username ? `@${u.username}` : u.name })
  }

  const topicOptions: { value: string; label: string }[] = []
  for (const pr of proposals) {
    if (pr.type === 'create_topic' && pr.name.trim()) {
      topicOptions.push({ value: pr.name.trim(), label: `${pr.icon || '📊'} ${pr.name.trim()} (new)` })
    }
  }
  for (const t of allTopics ?? []) {
    topicOptions.push({ value: t.name, label: `${t.icon || '📊'} ${t.name}` })
  }

  return (
    <div className="proposal-card editing">
      <div className="proposal-card-edit-header">
        <span className="proposal-card-type">{proposalIcon(p)}</span>
        <span style={{ flex: 1, fontWeight: 500, fontSize: '0.8125rem' }}>Edit Link</span>
        <button className="proposal-card-btn" onClick={onDone} title="Done"><Check size={14} /></button>
      </div>
      <div className="proposal-card-edit-fields">
        <div className="form-group">
          <label className="form-label">User</label>
          <select
            className="proposal-select"
            value={sp.user_ref}
            onChange={(e) => onChange({ ...sp, user_ref: e.target.value })}
          >
            <option value="">Select user...</option>
            {userOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Topic</label>
          <select
            className="proposal-select"
            value={sp.topic_ref}
            onChange={(e) => onChange({ ...sp, topic_ref: e.target.value })}
          >
            <option value="">Select topic...</option>
            {topicOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

// ─── Create/Edit Modal ───────────────────────────────────────

export interface CreateEditModalProps {
  open: boolean
  onClose: () => void
  /** When set, modal opens in edit mode for this entity */
  editEntity?: Topic | UserType | null
}

export function CreateEditModal({ open, onClose, editEntity }: CreateEditModalProps) {
  const isEditMode = !!editEntity
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)

  const { data: allUsers } = useListUsersQuery({ include_topics: true })
  const { data: allTopics } = useListTopicsQuery({ include_users: true })
  const [createTopic] = useCreateTopicMutation()
  const [createUser] = useCreateUserMutation()
  const [updateTopic] = useUpdateTopicMutation()
  const [updateUser] = useUpdateUserMutation()
  const [attachUser] = useAttachUserMutation()

  // Pre-populate when editing
  useEffect(() => {
    if (!open || !editEntity) return
    const _id = uid()
    if ('keywords' in editEntity) {
      // It's a Topic
      const t = editEntity as Topic
      setProposals([{
        _id,
        type: 'create_topic',
        name: t.name,
        icon: t.icon || '📊',
        description: t.description || '',
        platforms: t.platforms || ['x'],
        keywords: t.keywords || [],
        schedule_interval_hours: (t.config as Record<string, unknown>)?.schedule_interval_hours as number || 6,
      }])
    } else {
      // It's a User
      const u = editEntity as UserType
      setProposals([{
        _id,
        type: 'create_user',
        name: u.name,
        platform: u.platform || 'x',
        profile_url: u.profile_url || '',
        username: u.username || '',
        schedule_interval_hours: (u.config as Record<string, unknown>)?.schedule_interval_hours as number || 6,
      }])
    }
    setEditingId(_id)
  }, [open, editEntity])

  const buildBody = useCallback(
    (msgs: { role: string; content: string }[]) => {
      const body: Record<string, unknown> = { messages: msgs }
      if (editEntity) {
        // Send current config to backend so AI knows what's being edited
        if ('keywords' in editEntity) {
          const t = editEntity as Topic
          body.edit_context = {
            type: 'topic',
            id: t.id,
            name: t.name,
            icon: t.icon,
            description: t.description,
            platforms: t.platforms,
            keywords: t.keywords,
            schedule_interval_hours: (t.config as Record<string, unknown>)?.schedule_interval_hours || 6,
          }
        } else {
          const u = editEntity as UserType
          body.edit_context = {
            type: 'user',
            id: u.id,
            name: u.name,
            platform: u.platform,
            profile_url: u.profile_url,
            username: u.username,
            schedule_interval_hours: (u.config as Record<string, unknown>)?.schedule_interval_hours || 6,
          }
        }
      }
      return body
    },
    [editEntity],
  )

  const handleActions = useCallback((actions: Record<string, unknown>[]) => {
    const newProposals: Proposal[] = []
    const updates: { originalName: string; fields: Record<string, unknown>; type: 'create_topic' | 'create_user' }[] = []

    for (const a of actions) {
      const _id = uid()
      if (a.type === 'update_topic') {
        updates.push({ originalName: (a.original_name as string) || '', fields: a, type: 'create_topic' })
      } else if (a.type === 'update_user') {
        updates.push({ originalName: (a.original_name as string) || '', fields: a, type: 'create_user' })
      } else if (a.type === 'create_topic') {
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

    setProposals((prev) => {
      let updated = [...prev]

      for (const u of updates) {
        const idx = updated.findIndex((p) => p.type === u.type && ('name' in p) && p.name === u.originalName)
        if (idx !== -1) {
          const existing = updated[idx]
          if (u.type === 'create_topic' && existing.type === 'create_topic') {
            updated[idx] = {
              ...existing,
              ...(u.fields.name != null && { name: u.fields.name as string }),
              ...(u.fields.icon != null && { icon: u.fields.icon as string }),
              ...(u.fields.description != null && { description: u.fields.description as string }),
              ...(u.fields.platforms != null && { platforms: u.fields.platforms as string[] }),
              ...(u.fields.keywords != null && { keywords: u.fields.keywords as string[] }),
              ...(u.fields.schedule_interval_hours != null && { schedule_interval_hours: u.fields.schedule_interval_hours as number }),
            }
          } else if (u.type === 'create_user' && existing.type === 'create_user') {
            updated[idx] = {
              ...existing,
              ...(u.fields.name != null && { name: u.fields.name as string }),
              ...(u.fields.platform != null && { platform: u.fields.platform as string }),
              ...(u.fields.profile_url != null && { profile_url: u.fields.profile_url as string }),
              ...(u.fields.username != null && { username: u.fields.username as string }),
              ...(u.fields.schedule_interval_hours != null && { schedule_interval_hours: u.fields.schedule_interval_hours as number }),
            }
          }
          if (u.fields.name && u.fields.name !== u.originalName) {
            const newName = u.fields.name as string
            updated = updated.map((p) => {
              if (p.type !== 'subscribe') return p
              const sp = p as SubscribeProposal
              if (u.type === 'create_topic' && sp.topic_ref === u.originalName) {
                return { ...sp, topic_ref: newName }
              }
              if (u.type === 'create_user' && sp.user_ref === u.originalName) {
                return { ...sp, user_ref: newName }
              }
              return p
            })
          }
        }
      }

      // In edit mode, AI's update_topic/update_user may not match since
      // the proposal type is 'create_topic'/'create_user'. Apply updates
      // to the first proposal if no match was found and we're editing.
      if (isEditMode && updates.length > 0 && newProposals.length === 0) {
        for (const u of updates) {
          const idx = updated.findIndex((p) => p.type === u.type)
          if (idx !== -1) {
            const existing = updated[idx]
            if (u.type === 'create_topic' && existing.type === 'create_topic') {
              updated[idx] = {
                ...existing,
                ...(u.fields.name != null && { name: u.fields.name as string }),
                ...(u.fields.icon != null && { icon: u.fields.icon as string }),
                ...(u.fields.description != null && { description: u.fields.description as string }),
                ...(u.fields.platforms != null && { platforms: u.fields.platforms as string[] }),
                ...(u.fields.keywords != null && { keywords: u.fields.keywords as string[] }),
                ...(u.fields.schedule_interval_hours != null && { schedule_interval_hours: u.fields.schedule_interval_hours as number }),
              }
            } else if (u.type === 'create_user' && existing.type === 'create_user') {
              updated[idx] = {
                ...existing,
                ...(u.fields.name != null && { name: u.fields.name as string }),
                ...(u.fields.platform != null && { platform: u.fields.platform as string }),
                ...(u.fields.profile_url != null && { profile_url: u.fields.profile_url as string }),
                ...(u.fields.username != null && { username: u.fields.username as string }),
                ...(u.fields.schedule_interval_hours != null && { schedule_interval_hours: u.fields.schedule_interval_hours as number }),
              }
            }
          }
        }
      }

      return [...updated, ...newProposals]
    })
  }, [isEditMode])

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

  const addManual = (type: 'topic' | 'user' | 'link') => {
    const _id = uid()
    let p: Proposal
    if (type === 'topic') {
      p = { _id, type: 'create_topic', name: '', icon: '📊', description: '', platforms: ['x'], keywords: [], schedule_interval_hours: 6 }
    } else if (type === 'user') {
      p = { _id, type: 'create_user', name: '', platform: 'x', profile_url: '', username: '', schedule_interval_hours: 6 }
    } else {
      p = { _id, type: 'subscribe', user_ref: '', topic_ref: '' }
    }
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

    const setStatus = (id: string, status: Proposal['_status'], error?: string) => {
      if (status === 'error') failCount++
      setProposals((prev) => prev.map((p) => p._id === id ? { ...p, _status: status, _error: error } : p))
    }

    if (isEditMode && editEntity) {
      // ── Edit mode: update the single entity ──
      const p = proposals[0]
      if (!p) { setSubmitting(false); return }

      setStatus(p._id, 'creating')
      try {
        if (p.type === 'create_topic') {
          const tp = p as CreateTopicProposal
          await updateTopic({
            id: editEntity.id,
            name: tp.name.trim(),
            icon: tp.icon,
            description: tp.description || undefined,
            platforms: tp.platforms,
            keywords: tp.keywords,
            config: { ...((editEntity as Topic).config || {}), schedule_interval_hours: tp.schedule_interval_hours },
          }).unwrap()
        } else if (p.type === 'create_user') {
          const up = p as CreateUserProposal
          await updateUser({
            id: editEntity.id,
            name: up.name.trim(),
            platform: up.platform,
            profile_url: up.profile_url.trim(),
            username: up.username || undefined,
            config: { ...((editEntity as UserType).config || {}), schedule_interval_hours: up.schedule_interval_hours },
          }).unwrap()
        }
        setStatus(p._id, 'done')
      } catch (e) {
        setStatus(p._id, 'error', String(e))
      }
    } else {
      // ── Create mode ──

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
    }

    setSubmitting(false)

    if (failCount === 0) {
      setTimeout(() => { resetAll(); onClose() }, 600)
    }
  }

  const pendingCount = proposals.filter((p) => !p._status || p._status === 'pending' || p._status === 'error').length

  const chatPlaceholder = isEditMode
    ? 'Describe what you want to change...'
    : 'Describe what you want to monitor or follow...'

  const chatEmptyText = isEditMode
    ? ['Tell AI what you want to change,', 'or edit the fields below.']
    : ['Tell AI what you want to monitor or follow,', 'or add manually below.']

  return (
    <Modal open={open} onClose={() => { resetAll(); onClose() }} title={isEditMode ? 'Edit' : 'Create'} className="create-topic-panel">
      <div className="create-topic-content">
        {/* ── Chat Area ── */}
        <div className="create-topic-chat">
          <div className="create-topic-chat-messages">
            {chatMessages.length === 0 && !streamingReply && !isAssisting ? (
              <div className="create-topic-chat-empty">
                <Sparkles size={24} />
                {chatEmptyText.map((line, i) => <p key={i}>{line}</p>)}
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
              placeholder={chatPlaceholder}
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
              <span>{isEditMode ? 'Changes' : `Pending Actions (${proposals.length})`}</span>
            </div>
          )}
          <div className="proposal-list-cards">
            {proposals.map((p) => (
              <ProposalCard
                key={p._id}
                proposal={p}
                editing={editingId === p._id}
                editMode={isEditMode}
                onEdit={() => setEditingId(p._id)}
                onDone={() => setEditingId(null)}
                onChange={(updated) => setProposals((prev) => prev.map((x) => x._id === p._id ? updated : x))}
                onRemove={() => { setProposals((prev) => prev.filter((x) => x._id !== p._id)); if (editingId === p._id) setEditingId(null) }}
                proposals={proposals}
                allTopics={allTopics}
                allUsers={allUsers}
              />
            ))}
          </div>

          {/* Manual add — only in create mode */}
          {!isEditMode && !submitting && (
            <div className="proposal-manual">
              {manualOpen ? (
                <div className="proposal-manual-buttons">
                  <button className="proposal-manual-btn" onClick={() => addManual('topic')}>
                    <Sparkles size={12} /> + Topic
                  </button>
                  <button className="proposal-manual-btn" onClick={() => addManual('user')}>
                    <User size={12} /> + User
                  </button>
                  <button className="proposal-manual-btn" onClick={() => addManual('link')}>
                    <Link2 size={12} /> + Link
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

      {/* ── Submit ── */}
      <button
        className="btn btn-create"
        disabled={pendingCount === 0 || submitting}
        onClick={handleSubmitAll}
      >
        {submitting ? <Loader2 size={18} className="assist-spinner" /> : isEditMode ? <Check size={18} /> : <Plus size={18} />}
        <span className="btn-create-label">
          {submitting
            ? (isEditMode ? 'Saving...' : 'Creating...')
            : (isEditMode ? 'Save Changes' : `Submit All (${pendingCount})`)
          }
        </span>
      </button>
    </Modal>
  )
}
