import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type { Task, Job, AgentHeartbeat, QueueInfo, Content, BrowserCookie, CookiesPool, ChatMessage, HealthResponse, DashboardStats, Topic, User, PipelineDetail } from '@/types/models'

export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Task', 'Job', 'Agent', 'Content', 'Cookies', 'Topic', 'User'],
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
    listContents: builder.query<{ contents: Content[]; total: number }, { platform?: string; user_id?: string; limit?: number; offset?: number } | void>({
      query: (params) => ({ url: '/contents', params: params ?? undefined }),
      providesTags: ['Content'],
    }),
    getContent: builder.query<Content, string>({
      query: (id) => `/content/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Content', id }],
    }),
    getContentReplies: builder.query<{ replies: Content[]; total: number }, string>({
      query: (id) => `/content/${id}/replies`,
      providesTags: (_result, _error, id) => [{ type: 'Content', id: `${id}-replies` }],
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
    createTopic: builder.mutation<Topic, { type?: string; name: string; icon?: string; description?: string; platforms: string[]; keywords: string[]; config?: Record<string, unknown> }>({
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
    getTopicTrend: builder.query<{ day: string; posts: number; likes: number; views: number; retweets: number; replies: number; media_posts: number }[], string>({
      query: (id) => `/topics/${id}/trend`,
    }),
    reanalyzeTopic: builder.mutation<{ task_id: string }, string>({
      query: (id) => ({ url: `/topics/${id}/reanalyze`, method: 'POST' }),
      invalidatesTags: ['Topic'],
    }),
    getTopicPipeline: builder.query<PipelineDetail, string>({
      query: (id) => `/topics/${id}/pipeline`,
    }),
    reorderTopics: builder.mutation<{ status: string }, { pinned: string[]; unpinned: string[] }>({
      query: ({ pinned, unpinned }) => ({
        url: '/topics/reorder',
        method: 'POST',
        body: {
          items: [
            ...pinned.map((id, i) => ({ id, position: i, is_pinned: true })),
            ...unpinned.map((id, i) => ({ id, position: i, is_pinned: false })),
          ],
        },
      }),
      invalidatesTags: ['Topic'],
    }),

    // Users
    listUsers: builder.query<User[], { standalone?: boolean } | void>({
      query: (params) => ({ url: '/users', params: params ?? undefined }),
      transformResponse: (res: { users: User[] }) => res.users,
      providesTags: ['User'],
    }),
    getUser: builder.query<User, string>({
      query: (id) => `/users/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'User', id }],
    }),
    createUser: builder.mutation<User, { name: string; platform: string; profile_url: string; username?: string; config?: Record<string, unknown>; topic_ids?: string[] }>({
      query: (body) => ({ url: '/users', method: 'POST', body }),
      transformResponse: (res: { user: User }) => res.user,
      invalidatesTags: ['User', 'Topic'],
    }),
    updateUser: builder.mutation<User, { id: string } & Partial<{ name: string; platform: string; profile_url: string; username: string; config: Record<string, unknown>; status: string; is_pinned: boolean }>>({
      query: ({ id, ...body }) => ({ url: `/users/${id}`, method: 'PATCH', body }),
      invalidatesTags: ['User'],
    }),
    deleteUser: builder.mutation<{ deleted: string }, string>({
      query: (id) => ({ url: `/users/${id}`, method: 'DELETE' }),
      invalidatesTags: ['User', 'Topic'],
    }),
    attachUser: builder.mutation<{ status: string }, { userId: string; topicId: string }>({
      query: ({ userId, topicId }) => ({ url: `/users/${userId}/attach`, method: 'POST', body: { topic_id: topicId } }),
      invalidatesTags: ['User', 'Topic'],
    }),
    detachUser: builder.mutation<{ status: string }, { userId: string; topicId: string }>({
      query: ({ userId, topicId }) => ({ url: `/users/${userId}/detach`, method: 'POST', body: { topic_id: topicId } }),
      invalidatesTags: ['User', 'Topic'],
    }),
    reorderUsers: builder.mutation<{ status: string }, { pinned: string[]; unpinned: string[] }>({
      query: ({ pinned, unpinned }) => ({
        url: '/users/reorder',
        method: 'POST',
        body: {
          items: [
            ...pinned.map((id, i) => ({ id, position: i, is_pinned: true })),
            ...unpinned.map((id, i) => ({ id, position: i, is_pinned: false })),
          ],
        },
      }),
      invalidatesTags: ['User'],
    }),
    reanalyzeUser: builder.mutation<{ task_id: string }, string>({
      query: (id) => ({ url: `/users/${id}/reanalyze`, method: 'POST' }),
      invalidatesTags: ['User'],
    }),
    getUserPipeline: builder.query<PipelineDetail, string>({
      query: (id) => `/users/${id}/pipeline`,
    }),
    getUserTrend: builder.query<{ day: string; posts: number; likes: number; views: number; retweets: number; replies: number; media_posts: number }[], string>({
      query: (id) => `/users/${id}/trend`,
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
  useGetContentRepliesQuery,
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
  useGetTopicTrendQuery,
  useReanalyzeTopicMutation,
  useReorderTopicsMutation,
  useGetTopicPipelineQuery,
  useListUsersQuery,
  useGetUserQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useAttachUserMutation,
  useDetachUserMutation,
  useReorderUsersMutation,
  useReanalyzeUserMutation,
  useGetUserPipelineQuery,
  useGetUserTrendQuery,
} = apiSlice
