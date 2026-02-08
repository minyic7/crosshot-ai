import { useState } from 'react'
import { Database, LayoutGrid, List } from 'lucide-react'
import { TasksTable } from './TasksTable'
import { ContentGallery } from './ContentGallery'

type Tab = 'contents' | 'tasks'

export function DatabasePage() {
  const [activeTab, setActiveTab] = useState<Tab>('contents')

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'contents', label: 'Contents', icon: <LayoutGrid size={15} /> },
    { key: 'tasks', label: 'Tasks', icon: <List size={15} /> },
  ]

  return (
    <div className="stack">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database size={20} />
          <h1 className="text-xl font-semibold">Database</h1>
        </div>

        <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'rgba(100, 116, 139, 0.08)' }}>
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200"
              style={{
                background: activeTab === t.key ? 'white' : 'transparent',
                color: activeTab === t.key ? 'var(--foreground)' : 'var(--foreground-muted)',
                boxShadow: activeTab === t.key ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'contents' ? <ContentGallery /> : <TasksTable />}
    </div>
  )
}
