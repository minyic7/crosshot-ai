export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'
export type TaskPriority = 0 | 1 | 2

export interface Task {
  id: string
  label: string
  priority: TaskPriority
  status: TaskStatus
  payload: Record<string, unknown>
  parent_job_id: string | null
  assigned_to: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  retry_count: number
  max_retries: number
  error: string | null
  result: Record<string, unknown> | null
}

export interface Job {
  job_id: string
  status: string
  progress: {
    total: number
    completed: number
    failed: number
  }
}

export interface AgentHeartbeat {
  name: string
  labels: string[]
  status: 'idle' | 'busy' | 'error'
  current_task_id: string | null
  current_task_label: string | null
  tasks_completed: number
  tasks_failed: number
  started_at: string
  last_heartbeat: string
}

export interface QueueInfo {
  label: string
  pending: number
}

export interface Content {
  id: string
  task_id: string
  platform: string
  source_url: string
  crawled_at: string
  data: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface BrowserCookie {
  name: string
  value: string
  domain: string
  path: string
  expirationDate?: number
  httpOnly?: boolean
  secure?: boolean
  sameSite?: string
  session?: boolean
  [key: string]: unknown
}

export interface CookiesPool {
  id: string
  platform: string
  name: string
  cookies: BrowserCookie[]
  is_active: boolean
  last_used_at: string | null
  use_count_today: number
  fail_count: number
  cooldown_until: string | null
}

export interface HealthResponse {
  status: string
}

export interface DashboardStats {
  agents_online: number
  agents_busy: number
  total_pending: number
  recent_completed: number
  recent_failed: number
  queues: Record<string, number>
}
