import { LayoutDashboard, Bot, FileText, Settings, Search, Plus } from "lucide-react"

interface NavItem {
  icon: React.ReactNode
  label: string
  href: string
  active?: boolean
}

const navItems: NavItem[] = [
  { icon: <LayoutDashboard size={16} />, label: "Dashboard", href: "/", active: true },
  { icon: <Bot size={16} />, label: "Agents", href: "/agents" },
  { icon: <FileText size={16} />, label: "Content", href: "/content" },
  { icon: <Search size={16} />, label: "Keywords", href: "/keywords" },
  { icon: <Settings size={16} />, label: "Settings", href: "/settings" },
]

export { navItems }

export function TopNav() {
  return (
    <header className="topnav">
      <div className="topnav-inner">
        {/* Left: Logo + Brand */}
        <div className="topnav-brand">
          <div className="topnav-logo">
            <span>C</span>
          </div>
          <div>
            <span className="topnav-brand-name">Crosshot</span>
            <span className="topnav-brand-suffix">AI</span>
          </div>
        </div>

        {/* Center: Nav Links (desktop only) */}
        <nav className="topnav-links">
          {navItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`topnav-link ${item.active ? "active" : ""}`}
            >
              {item.icon}
              {item.label}
            </a>
          ))}
        </nav>

        {/* Right: Search + Status + CTA (desktop only) */}
        <div className="topnav-actions">
          <div className="topnav-search">
            <Search size={14} className="topnav-search-icon" />
            <input type="text" placeholder="Search...  ⌘K" />
          </div>
          <div className="topnav-status">
            <div className="status-dot online" />
            <span>Online</span>
          </div>
          <button className="topnav-cta">
            <Plus size={14} />
            New Crawler
          </button>
        </div>

        {/* Mobile: Search icon only */}
        <button className="topnav-mobile-search-btn" aria-label="Search">
          <Search size={18} />
        </button>
      </div>
    </header>
  )
}
