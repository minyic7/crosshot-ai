import { useState } from 'react'
import { TasksTable } from './TasksTable'
import { ContentsTable } from './ContentsTable'

type Tab = 'tasks' | 'contents'

export function DatabasePage() {
  const [activeTab, setActiveTab] = useState<Tab>('tasks')

  return (
    <div className="stack">
      <h1 className="text-xl font-semibold">Database</h1>

      <div className="flex gap-2">
        <button
          className={`btn ${activeTab === 'tasks' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('tasks')}
        >
          Tasks
        </button>
        <button
          className={`btn ${activeTab === 'contents' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('contents')}
        >
          Contents
        </button>
      </div>

      {activeTab === 'tasks' ? <TasksTable /> : <ContentsTable />}
    </div>
  )
}
