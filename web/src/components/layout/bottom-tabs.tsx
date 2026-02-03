import { LayoutDashboard, Bot, FileText, Search, Settings } from "lucide-react"

interface TabItem {
  icon: React.ReactNode
  label: string
  href: string
  active?: boolean
}

const tabItems: TabItem[] = [
  { icon: <LayoutDashboard size={20} />, label: "Dashboard", href: "/", active: true },
  { icon: <Bot size={20} />, label: "Agents", href: "/agents" },
  { icon: <FileText size={20} />, label: "Content", href: "/content" },
  { icon: <Search size={20} />, label: "Keywords", href: "/keywords" },
  { icon: <Settings size={20} />, label: "Settings", href: "/settings" },
]

export function BottomTabs() {
  return (
    <nav className="bottom-tabs">
      {tabItems.map((tab) => (
        <a
          key={tab.href}
          href={tab.href}
          className={`bottom-tab ${tab.active ? "active" : ""}`}
        >
          {tab.icon}
          <span>{tab.label}</span>
        </a>
      ))}
    </nav>
  )
}
