import { Outlet } from 'react-router-dom'
import { TopNav } from './TopNav'
import { BottomTabs } from './BottomTabs'

export function Layout() {
  return (
    <div className="app-layout">
      <TopNav />
      <main className="main-content">
        <div className="page-container">
          <Outlet />
        </div>
      </main>
      <BottomTabs />
    </div>
  )
}
