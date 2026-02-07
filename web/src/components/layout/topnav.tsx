import { useState, useRef, useEffect } from "react"
import { NavLink } from "react-router-dom"
import { LayoutDashboard, Bot, Settings, Search, Database, X } from "lucide-react"

interface NavItem {
  icon: React.ReactNode
  label: string
  href: string
}

const navItems: NavItem[] = [
  { icon: <LayoutDashboard size={16} />, label: "Dashboard", href: "/" },
  { icon: <Database size={16} />, label: "Database", href: "/database" },
  { icon: <Bot size={16} />, label: "Agents", href: "/agents" },
  { icon: <Settings size={16} />, label: "Settings", href: "/settings" },
]

export { navItems }

export function TopNav() {
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const mobileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (mobileSearchOpen) {
      mobileInputRef.current?.focus()
    }
  }, [mobileSearchOpen])

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
            <NavLink
              key={item.href}
              to={item.href}
              end={item.href === "/"}
              className={({ isActive }) =>
                `topnav-link ${isActive ? "active" : ""}`
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Right: Search + Status + CTA (desktop only) */}
        <div className="topnav-actions">
          <div className="topnav-search">
            <Search size={14} className="topnav-search-icon" />
            <input type="text" placeholder="Search...  ⌘K" />
          </div>
        </div>

        {/* Mobile: Search icon toggle */}
        <button
          className="topnav-mobile-search-btn"
          aria-label="Search"
          onClick={() => setMobileSearchOpen((o) => !o)}
        >
          {mobileSearchOpen ? <X size={18} /> : <Search size={18} />}
        </button>
      </div>

      {/* Mobile: Expanded search bar */}
      {mobileSearchOpen && (
        <div className="topnav-mobile-search-bar">
          <Search size={14} className="topnav-search-icon" />
          <input
            ref={mobileInputRef}
            type="text"
            placeholder="Search..."
            onKeyDown={(e) => {
              if (e.key === "Escape") setMobileSearchOpen(false)
            }}
          />
        </div>
      )}
    </header>
  )
}
