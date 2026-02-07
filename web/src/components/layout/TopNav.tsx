import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Database, Bot, ListTodo, Cookie, MessageSquare } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/database', label: 'Database', icon: Database },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/tasks', label: 'Tasks', icon: ListTodo },
  { to: '/cookies', label: 'Cookies', icon: Cookie },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
]

export function TopNav() {
  return (
    <nav className="topnav">
      <div className="topnav-inner">
        <div className="topnav-brand">
          <span className="topnav-logo">Crosshot AI</span>
        </div>
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
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  )
}
