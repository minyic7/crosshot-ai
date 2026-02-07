import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type { Task, Job, Agent, Content, ChatMessage, HealthResponse } from '@/types/models'

export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Task', 'Job', 'Agent', 'Content'],
  endpoints: (builder) => ({
    // Health (at root, not /api)
    getHealth: builder.query<HealthResponse, void>({
      query: () => ({ url: '/health', baseUrl: '' }),
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
    listAgents: builder.query<Agent[], void>({
      query: () => '/agents',
      providesTags: ['Agent'],
    }),
    getAgentLogs: builder.query<{ logs: string[] }, { name: string; lines?: number }>({
      query: ({ name, lines = 100 }) => `/agents/${name}/logs?lines=${lines}`,
    }),

    // Contents
    listContents: builder.query<{ contents: Content[]; total: number }, { platform?: string; limit?: number; offset?: number } | void>({
      query: (params) => ({ url: '/contents', params: params ?? undefined }),
      providesTags: ['Content'],
    }),

    // Chat
    sendChatMessage: builder.mutation<ChatMessage, { message: string }>({
      query: (body) => ({ url: '/chat', method: 'POST', body }),
    }),
  }),
})

export const {
  useGetHealthQuery,
  useListTasksQuery,
  useGetTaskQuery,
  useCreateJobMutation,
  useGetJobQuery,
  useListAgentsQuery,
  useGetAgentLogsQuery,
  useListContentsQuery,
  useSendChatMessageMutation,
} = apiSlice
