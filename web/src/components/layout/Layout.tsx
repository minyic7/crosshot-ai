import { Outlet } from 'react-router-dom'
import { TopNav } from './TopNav'
import { BottomTabs } from './BottomTabs'
import { useTheme } from '@/hooks/useTheme'

export function Layout() {
  const { theme, toggle } = useTheme()

  return (
    <div className="app-layout">
      {/* Floating background blobs */}
      <div className="blobs-container">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
        <div className="blob blob-4" />
      </div>

      <TopNav theme={theme} onToggleTheme={toggle} />
      <main className="main-content">
        <div className="page-container">
          <Outlet />
        </div>
      </main>
      <BottomTabs />
    </div>
  )
}
