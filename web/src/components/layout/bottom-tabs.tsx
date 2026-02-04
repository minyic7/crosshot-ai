import { NavLink } from "react-router-dom"
import { LayoutDashboard, Bot, Database, Settings } from "lucide-react"

interface TabItem {
  icon: React.ReactNode
  label: string
  href: string
}

const tabItems: TabItem[] = [
  { icon: <LayoutDashboard size={20} />, label: "Dashboard", href: "/" },
  { icon: <Database size={20} />, label: "Database", href: "/database" },
  { icon: <Bot size={20} />, label: "Agents", href: "/agents" },
  { icon: <Settings size={20} />, label: "Settings", href: "/settings" },
]

export function BottomTabs() {
  return (
    <nav className="bottom-tabs">
      {tabItems.map((tab) => (
        <NavLink
          key={tab.href}
          to={tab.href}
          end={tab.href === "/"}
          className={({ isActive }) =>
            `bottom-tab ${isActive ? "active" : ""}`
          }
        >
          {tab.icon}
          <span>{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
