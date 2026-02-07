import { Routes, Route } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { DatabasePage } from '@/features/database/DatabasePage'
import { AgentsPage } from '@/features/agents/AgentsPage'
import { TasksPage } from '@/features/tasks/TasksPage'
import { ChatPage } from '@/features/chat/ChatPage'

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="database" element={<DatabasePage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="chat" element={<ChatPage />} />
      </Route>
    </Routes>
  )
}
