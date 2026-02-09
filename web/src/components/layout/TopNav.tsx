import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Database, Bot, ListTodo, Cookie, MessageSquare, Sun, Moon } from 'lucide-react'
import { useGetHealthQuery } from '@/store/api'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/database', label: 'Database', icon: Database },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/tasks', label: 'Tasks', icon: ListTodo },
  { to: '/cookies', label: 'Cookies', icon: Cookie },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
]

export function TopNav({ theme, onToggleTheme }: { theme: 'light' | 'dark'; onToggleTheme: () => void }) {
  const { data: health } = useGetHealthQuery(undefined, { pollingInterval: 10000 })
  const online = health?.status === 'ok'

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
