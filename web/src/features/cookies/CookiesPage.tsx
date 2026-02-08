import { useState } from 'react'
import { Cookie, Plus, Trash2, Power, ChevronDown, ChevronUp, Clock, AlertTriangle, Timer } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Skeleton } from '@/components/ui/Skeleton'
import {
  useListCookiesQuery,
  useCreateCookiesMutation,
  useUpdateCookiesMutation,
  useDeleteCookiesMutation,
} from '@/store/api'
import type { CookiesPool, BrowserCookie } from '@/types/models'

export function CookiesPage() {
  const [platformFilter, setPlatformFilter] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  const { data: cookies, isLoading } = useListCookiesQuery(
    platformFilter ? { platform: platformFilter } : undefined,
    { pollingInterval: 10000 },
  )
  const [updateCookies] = useUpdateCookiesMutation()
  const [deleteCookies] = useDeleteCookiesMutation()

  const handleToggle = async (cookie: CookiesPool) => {
    await updateCookies({ id: cookie.id, is_active: !cookie.is_active })
  }

  const handleDelete = async (id: string) => {
    await deleteCookies(id)
  }

  return (
    <div className="stack">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cookie size={20} />
          <h1 className="text-xl font-semibold">Cookies Pool</h1>
        </div>
        <Button onClick={() => setShowAddModal(true)}>
          <Plus size={14} />
          Add Cookies
        </Button>
      </div>

      {/* Platform filter */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium" style={{ color: 'var(--foreground-muted)' }}>Platform:</span>
        {['', 'x', 'xhs'].map((p) => (
          <button
            key={p}
            className={`btn btn-sm ${platformFilter === p ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setPlatformFilter(p)}
          >
            {p || 'All'}
          </button>
        ))}
      </div>

      {/* Cookies list */}
      {isLoading ? (
        <div className="stack-sm">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="w-full h-24" />
          ))}
        </div>
      ) : cookies && cookies.length > 0 ? (
        <div className="stack-sm">
          {cookies.map((cookie) => (
            <CookieCard
              key={cookie.id}
              cookie={cookie}
              onToggle={() => handleToggle(cookie)}
              onDelete={() => handleDelete(cookie.id)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent>
            <p className="py-8 text-center" style={{ color: 'var(--foreground-subtle)' }}>
              No cookies yet. Add some to get started.
            </p>
          </CardContent>
        </Card>
      )}

      {showAddModal && (
        <AddCookiesModal onClose={() => setShowAddModal(false)} />
      )}
    </div>
  )
}

// ──────────────────────────────────────────────
// Cookie Card
// ──────────────────────────────────────────────

function CookieCard({
  cookie,
  onToggle,
  onDelete,
}: {
  cookie: CookiesPool
  onToggle: () => void
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  // Auth-critical cookies and their expiry
  const AUTH_KEYS = ['auth_token', 'ct0', 'twid', 'kdt']
  const authCookies = cookie.cookies.filter((c) => AUTH_KEYS.includes(c.name))
  const authExpiry = authCookies
    .filter((c) => c.expirationDate)
    .reduce((min, c) => (c.expirationDate! < min ? c.expirationDate! : min), Infinity)
  const missingAuth = AUTH_KEYS.filter((k) => !authCookies.find((c) => c.name === k))

  const inCooldown = cookie.cooldown_until && new Date(cookie.cooldown_until).getTime() > Date.now()

  return (
    <Card className={cookie.is_active ? '' : 'opacity-60'}>
      <CardContent>
        {/* Header row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Badge variant={cookie.is_active ? 'success' : 'muted'}>
              {cookie.platform.toUpperCase()}
            </Badge>
            <span className="font-medium">{cookie.name}</span>
            <span className="text-sm font-mono" style={{ color: 'var(--foreground-muted)' }}>
              {cookie.id.slice(0, 8)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onToggle}>
              <Power size={14} />
              {cookie.is_active ? 'Disable' : 'Enable'}
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              <Trash2 size={14} />
            </Button>
          </div>
        </div>

        {/* Auth status row */}
        <div className="flex items-center gap-3 mt-2 flex-wrap">
          <Badge variant="muted">{cookie.cookies.length} cookies</Badge>
          {authExpiry < Infinity ? (
            <Badge variant={isExpired(authExpiry) ? 'error' : isExpiringSoon(authExpiry) ? 'warning' : 'success'}>
              {isExpired(authExpiry) ? 'Auth expired' : `Auth valid ${formatExpiry(authExpiry)}`}
            </Badge>
          ) : authCookies.length === 0 ? (
            <Badge variant="error">No auth tokens</Badge>
          ) : null}
          {missingAuth.length > 0 && (
            <span className="text-xs" style={{ color: 'var(--warning)' }}>
              Missing: {missingAuth.join(', ')}
            </span>
          )}
        </div>

        {/* Usage & health metrics */}
        <div
          className="flex items-center gap-4 mt-3 flex-wrap"
          style={{
            padding: '8px 12px',
            borderRadius: 8,
            background: 'rgba(100, 116, 139, 0.04)',
            border: '1px solid rgba(100, 116, 139, 0.08)',
          }}
        >
          {cookie.use_count_today > 0 && (
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--foreground-muted)' }}>
              <Timer size={12} />
              <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {cookie.use_count_today}
              </span>
              used today
            </span>
          )}
          {cookie.fail_count > 0 && (
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--error)' }}>
              <AlertTriangle size={12} />
              <span style={{ fontWeight: 600 }}>{cookie.fail_count}</span>
              {cookie.fail_count === 1 ? 'failure' : 'failures'}
            </span>
          )}
          {inCooldown && (
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--warning)' }}>
              <Clock size={12} />
              Cooldown until {new Date(cookie.cooldown_until!).toLocaleTimeString()}
            </span>
          )}
          {cookie.last_used_at && (
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--foreground-subtle)' }}>
              <Clock size={12} />
              Last used {formatTimeAgo(cookie.last_used_at)}
            </span>
          )}
          {!cookie.use_count_today && !cookie.fail_count && !inCooldown && !cookie.last_used_at && (
            <span className="text-xs" style={{ color: 'var(--foreground-subtle)' }}>
              No activity yet
            </span>
          )}
        </div>

        {/* Expand toggle */}
        <button
          className="flex items-center gap-1 text-sm mt-3"
          style={{ color: 'var(--foreground-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? 'Hide details' : 'Show details'}
        </button>

        {/* Cookies table */}
        {expanded && (
          <div className="mt-2 overflow-auto" style={{ maxHeight: '300px' }}>
            <div className="table-compact">
              <div className="table-compact-row" style={{ fontWeight: 600, borderBottom: '2px solid #e5e7eb', fontSize: '0.75rem' }}>
                <span style={{ flex: 1.2 }}>Name</span>
                <span style={{ flex: 1 }}>Domain</span>
                <span style={{ flex: 1 }}>Expires</span>
                <span style={{ flex: 0.5 }}>Flags</span>
              </div>
              {cookie.cookies.map((c, i) => (
                <div key={i} className="table-compact-row" style={{ fontSize: '0.75rem' }}>
                  <span style={{ flex: 1.2, fontWeight: AUTH_KEYS.includes(c.name) ? 600 : 400 }} className="font-mono">
                    {AUTH_KEYS.includes(c.name) ? '\u2605 ' : ''}{c.name}
                  </span>
                  <span style={{ flex: 1 }} className="font-mono">{c.domain}</span>
                  <span style={{ flex: 1 }}>
                    {c.expirationDate ? (
                      <span className={isExpired(c.expirationDate) ? 'text-red-500' : ''}>
                        {formatExpiry(c.expirationDate)}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--foreground-muted)' }}>session</span>
                    )}
                  </span>
                  <span style={{ flex: 0.5 }} className="flex gap-1">
                    {c.httpOnly && <Badge variant="muted">H</Badge>}
                    {c.secure && <Badge variant="muted">S</Badge>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ──────────────────────────────────────────────
// Add Cookies Modal
// ──────────────────────────────────────────────

function AddCookiesModal({ onClose }: { onClose: () => void }) {
  const [platform, setPlatform] = useState('x')
  const [name, setName] = useState('')
  const [cookiesJson, setCookiesJson] = useState('')
  const [error, setError] = useState('')
  const [createCookies, { isLoading }] = useCreateCookiesMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Name is required')
      return
    }
    if (!cookiesJson.trim()) {
      setError('Cookies JSON is required')
      return
    }

    let parsed: BrowserCookie[]
    try {
      const raw = JSON.parse(cookiesJson)
      if (!Array.isArray(raw)) {
        setError('Cookies must be a JSON array')
        return
      }
      parsed = raw
    } catch {
      setError('Invalid JSON')
      return
    }

    await createCookies({ platform, name: name.trim(), cookies: parsed })
    onClose()
  }

  return (
    <Modal open title="Add Cookies" onClose={onClose}>
      <form onSubmit={handleSubmit} className="stack-sm">
        <div className="form-group">
          <label className="form-label">Platform</label>
          <div className="flex gap-2">
            {['x', 'xhs'].map((p) => (
              <button
                key={p}
                type="button"
                className={`btn btn-sm ${platform === p ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setPlatform(p)}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="cookie-name">Account Name</label>
          <input
            id="cookie-name"
            className="form-input"
            placeholder="e.g. my-x-account"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="cookie-json">
            Cookies (JSON array from browser export)
          </label>
          <textarea
            id="cookie-json"
            className="form-textarea"
            placeholder='[{"name": "auth_token", "value": "...", "domain": ".x.com", ...}]'
            value={cookiesJson}
            onChange={(e) => setCookiesJson(e.target.value)}
            rows={8}
          />
        </div>

        {error && (
          <p className="text-sm" style={{ color: 'var(--error)' }}>{error}</p>
        )}

        <div className="flex gap-2">
          <Button type="submit" disabled={isLoading}>
            {isLoading ? 'Adding...' : 'Add'}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function formatExpiry(unixTimestamp: number): string {
  const date = new Date(unixTimestamp * 1000)
  const now = Date.now()
  const diff = date.getTime() - now

  if (diff < 0) return 'Expired'

  const days = Math.floor(diff / 86400000)
  if (days > 365) return `${Math.floor(days / 365)}y ${days % 365}d`
  if (days > 30) return `${Math.floor(days / 30)}mo ${days % 30}d`
  if (days > 0) return `${days}d`

  const hours = Math.floor(diff / 3600000)
  if (hours > 0) return `${hours}h`
  return `${Math.floor(diff / 60000)}m`
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function isExpired(unixTimestamp: number): boolean {
  return unixTimestamp * 1000 < Date.now()
}

function isExpiringSoon(unixTimestamp: number): boolean {
  const threeDays = 3 * 86400 * 1000
  return unixTimestamp * 1000 - Date.now() < threeDays
}
