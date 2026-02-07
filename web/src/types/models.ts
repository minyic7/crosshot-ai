export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'
export type TaskPriority = 0 | 1 | 2

export interface Task {
  id: string
  label: string
  priority: TaskPriority
  status: TaskStatus
  payload: Record<string, unknown>
  parent_job_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  retry_count: number
  max_retries: number
  error: string | null
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

export interface Agent {
  name: string
  labels: string[]
  status: 'running' | 'stopped' | 'error'
  ai_enabled: boolean
  tasks_completed: number
  tasks_failed: number
  uptime_seconds: number
  last_heartbeat: string | null
}

export interface Content {
  id: string
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

export interface HealthResponse {
  status: string
}
