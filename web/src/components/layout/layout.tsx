import { TopNav } from "./topnav"
import { BottomTabs } from "./bottom-tabs"
import { Fab } from "./fab"
import type { ReactNode } from "react"

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="app-layout">
      <TopNav />
      <main className="main-content">
        {children}
      </main>
      <BottomTabs />
      <Fab />
    </div>
  )
}
