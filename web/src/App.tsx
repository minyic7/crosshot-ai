import { Routes, Route } from 'react-router-dom'
import { TimezoneProvider } from '@/hooks/useTimezone'
import { Layout } from '@/components/layout/Layout'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { DatabasePage } from '@/features/database/DatabasePage'
import { AgentsPage } from '@/features/agents/AgentsPage'
import { TasksPage } from '@/features/tasks/TasksPage'
import { ChatPage } from '@/features/chat/ChatPage'
import { CookiesPage } from '@/features/cookies/CookiesPage'
import { ContentDetailPage } from '@/features/database/ContentDetailPage'
import { TaskDetailPage } from '@/features/database/TaskDetailPage'
import { TopicDetailPage } from '@/features/dashboard/TopicDetailPage'

export function App() {
  return (
    <TimezoneProvider>
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="topic/:id" element={<TopicDetailPage />} />
        <Route path="database" element={<DatabasePage />} />
        <Route path="content/:id" element={<ContentDetailPage />} />
        <Route path="task/:id" element={<TaskDetailPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="cookies" element={<CookiesPage />} />
        <Route path="chat" element={<ChatPage />} />
      </Route>
    </Routes>
    </TimezoneProvider>
  )
}
