import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Bot, ListTodo, Cookie, MessageSquare } from 'lucide-react'

const tabItems = [
  { to: '/', label: 'Home', icon: LayoutDashboard },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/tasks', label: 'Tasks', icon: ListTodo },
  { to: '/cookies', label: 'Cookies', icon: Cookie },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
]

export function BottomTabs() {
  return (
    <nav className="bottom-tabs">
      {tabItems.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `bottom-tab${isActive ? ' active' : ''}`
          }
        >
          <Icon size={20} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
