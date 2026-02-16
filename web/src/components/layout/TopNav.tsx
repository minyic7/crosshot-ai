import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Database, Bot, Cookie, Sun, Moon, Globe } from 'lucide-react'
import { useGetHealthQuery } from '@/store/api'
import { useTimezone } from '@/hooks/useTimezone'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/database', label: 'Database', icon: Database },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/cookies', label: 'Cookies', icon: Cookie },
]

export function TopNav({ theme, onToggleTheme }: { theme: 'light' | 'dark'; onToggleTheme: () => void }) {
  const { data: health } = useGetHealthQuery(undefined, { pollingInterval: 10000 })
  const online = health?.status === 'ok'
  const { tz, options, setTz, tzLabel } = useTimezone()

  return (
    <nav className="topnav">
      <div className="topnav-inner">
        {/* Brand */}
        <div className="topnav-brand">
          <div className="topnav-logo">
            <span>C</span>
          </div>
          <span className="topnav-brand-name">
            CrossHot<span className="topnav-brand-suffix">AI</span>
          </span>
        </div>

        {/* Nav links */}
        <div className="topnav-links">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `topnav-link${isActive ? ' active' : ''}`
              }
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </div>

        {/* Right side: theme toggle + connection status */}
        <div className="topnav-actions">
          <button
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
          >
            <div className={`theme-toggle-knob ${theme}`}>
              {theme === 'light' ? <Sun size={13} color="#fff" strokeWidth={2.5} /> : <Moon size={13} color="#fff" strokeWidth={2.5} />}
            </div>
          </button>

          <div className="tz-selector">
            <Globe size={13} />
            <select value={tz} onChange={(e) => setTz(e.target.value as typeof tz)}>
              {options.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className="tz-label">{tzLabel}</span>
          </div>

          <div className={`connection-pill ${online ? 'online' : 'offline'}`}>
            <span className="connection-dot">
              <span className="connection-dot-inner" />
              {online && <span className="connection-dot-ring" />}
            </span>
            {online ? 'Connected' : 'Offline'}
          </div>
        </div>
      </div>
    </nav>
  )
}
