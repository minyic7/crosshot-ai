import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type { Task, Job, AgentHeartbeat, QueueInfo, Content, BrowserCookie, CookiesPool, ChatMessage, HealthResponse, DashboardStats, Topic } from '@/types/models'

export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Task', 'Job', 'Agent', 'Content', 'Cookies', 'Topic'],
  endpoints: (builder) => ({
    // Health (at root, not /api)
    getHealth: builder.query<HealthResponse, void>({
      query: () => ({ url: '/health', baseUrl: '' }),
    }),

    // Dashboard
    getDashboardStats: builder.query<DashboardStats, void>({
      query: () => '/dashboard/stats',
    }),

    // Tasks
    listTasks: builder.query<{ tasks: Task[]; total: number }, { label?: string; status?: string; limit?: number } | void>({
      query: (params) => ({ url: '/tasks', params: params ?? undefined }),
      providesTags: ['Task'],
    }),
    getTask: builder.query<Task, string>({
      query: (id) => `/tasks/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Task', id }],
    }),

    createTask: builder.mutation<{ task_id: string; label: string; status: string }, { label: string; payload: Record<string, unknown>; priority?: number }>({
      query: (body) => ({ url: '/tasks', method: 'POST', body }),
      invalidatesTags: ['Task'],
    }),

    // Jobs
    createJob: builder.mutation<{ job_id: string; status: string; tasks_created: number }, { description: string }>({
      query: (body) => ({ url: '/jobs', method: 'POST', body }),
      invalidatesTags: ['Task', 'Job'],
    }),
    getJob: builder.query<Job, string>({
      query: (id) => `/jobs/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Job', id }],
    }),

    // Agents
    listAgents: builder.query<AgentHeartbeat[], void>({
      query: () => '/agents',
      providesTags: ['Agent'],
    }),
    listQueues: builder.query<QueueInfo[], void>({
      query: () => '/agents/queues',
    }),

    // Contents
    listContents: builder.query<{ contents: Content[]; total: number }, { platform?: string; limit?: number; offset?: number } | void>({
      query: (params) => ({ url: '/contents', params: params ?? undefined }),
      providesTags: ['Content'],
    }),
    getContent: builder.query<Content, string>({
      query: (id) => `/content/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Content', id }],
    }),

    // Cookies
    listCookies: builder.query<CookiesPool[], { platform?: string } | void>({
      query: (params) => ({ url: '/cookies', params: params ?? undefined }),
      providesTags: ['Cookies'],
    }),
    createCookies: builder.mutation<CookiesPool, { platform: string; name: string; cookies: BrowserCookie[] }>({
      query: (body) => ({ url: '/cookies', method: 'POST', body }),
      invalidatesTags: ['Cookies'],
    }),
    updateCookies: builder.mutation<CookiesPool, { id: string; name?: string; cookies?: BrowserCookie[]; is_active?: boolean }>({
      query: ({ id, ...body }) => ({ url: `/cookies/${id}`, method: 'PATCH', body }),
      invalidatesTags: ['Cookies'],
    }),
    deleteCookies: builder.mutation<{ deleted: string }, string>({
      query: (id) => ({ url: `/cookies/${id}`, method: 'DELETE' }),
      invalidatesTags: ['Cookies'],
    }),

    // Chat
    sendChatMessage: builder.mutation<ChatMessage, { message: string }>({
      query: (body) => ({ url: '/chat', method: 'POST', body }),
    }),

    // Topics
    listTopics: builder.query<Topic[], void>({
      query: () => '/topics',
      transformResponse: (res: { topics: Topic[] }) => res.topics,
      providesTags: ['Topic'],
    }),
    getTopic: builder.query<Topic, string>({
      query: (id) => `/topics/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Topic', id }],
    }),
    createTopic: builder.mutation<Topic, { name: string; icon?: string; description?: string; platforms: string[]; keywords: string[]; config?: Record<string, unknown> }>({
      query: (body) => ({ url: '/topics', method: 'POST', body }),
      transformResponse: (res: { topic: Topic }) => res.topic,
      invalidatesTags: ['Topic'],
    }),
    updateTopic: builder.mutation<Topic, { id: string } & Partial<{ name: string; icon: string; description: string; platforms: string[]; keywords: string[]; config: Record<string, unknown>; status: string; is_pinned: boolean }>>({
      query: ({ id, ...body }) => ({ url: `/topics/${id}`, method: 'PATCH', body }),
      invalidatesTags: ['Topic'],
    }),
    deleteTopic: builder.mutation<{ deleted: string }, string>({
      query: (id) => ({ url: `/topics/${id}`, method: 'DELETE' }),
      invalidatesTags: ['Topic'],
    }),
    refreshTopic: builder.mutation<{ task_id: string }, string>({
      query: (id) => ({ url: `/topics/${id}/refresh`, method: 'POST' }),
      invalidatesTags: ['Topic'],
    }),
    reorderTopics: builder.mutation<{ status: string }, { ids: string[] }>({
      query: ({ ids }) => ({
        url: '/topics/reorder',
        method: 'POST',
        body: { items: ids.map((id, i) => ({ id, position: i })) },
      }),
      invalidatesTags: ['Topic'],
    }),
  }),
})

export const {
  useGetHealthQuery,
  useGetDashboardStatsQuery,
  useListTasksQuery,
  useGetTaskQuery,
  useCreateTaskMutation,
  useCreateJobMutation,
  useGetJobQuery,
  useListAgentsQuery,
  useListQueuesQuery,
  useListContentsQuery,
  useGetContentQuery,
  useListCookiesQuery,
  useCreateCookiesMutation,
  useUpdateCookiesMutation,
  useDeleteCookiesMutation,
  useSendChatMessageMutation,
  useListTopicsQuery,
  useGetTopicQuery,
  useCreateTopicMutation,
  useUpdateTopicMutation,
  useDeleteTopicMutation,
  useRefreshTopicMutation,
  useReorderTopicsMutation,
} = apiSlice
