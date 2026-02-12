import { useState, useRef, useEffect, useCallback } from 'react'
import type { ChatMsg } from '@/types/chat'

// ─── Helpers ──────────────────────────────────────────────────

/** Extract the "reply" value from a partial JSON string being streamed token-by-token. */
function extractReplyFromPartial(raw: string): string {
  const idx = raw.indexOf('"reply"')
  if (idx === -1) return ''
  const valStart = raw.indexOf('"', idx + 7)
  if (valStart === -1) return ''
  let result = ''
  let i = valStart + 1
  while (i < raw.length) {
    if (raw[i] === '\\' && i + 1 < raw.length) {
      const next = raw[i + 1]
      if (next === '"') result += '"'
      else if (next === 'n') result += '\n'
      else if (next === '\\') result += '\\'
      else result += next
      i += 2
    } else if (raw[i] === '"') {
      break
    } else {
      result += raw[i]
      i++
    }
  }
  return result
}

// ─── Hook ─────────────────────────────────────────────────────

interface UseSSEChatOptions {
  /** POST endpoint URL */
  endpoint: string
  /** Build the JSON body from the current message history */
  buildBody: (messages: ChatMsg[]) => object
  /**
   * - `'assist'`: accumulates raw tokens, uses extractReplyFromPartial(),
   *   handles `done` event with reply + suggestion
   * - `'direct'`: evt.t tokens are the reply text, appended to last message
   */
  mode: 'assist' | 'direct'
  /** Called when a suggestion is received (assist mode only) */
  onSuggestion?: (suggestion: Record<string, unknown>) => void
}

interface UseSSEChatReturn {
  messages: ChatMsg[]
  input: string
  setInput: (v: string) => void
  streaming: boolean
  /** Partial reply text during streaming (assist mode only) */
  streamingText: string
  send: () => Promise<void>
  reset: () => void
  scrollRef: React.RefObject<HTMLDivElement | null>
  handleKeyDown: (e: React.KeyboardEvent) => void
}

export function useSSEChat({
  endpoint,
  buildBody,
  mode,
  onSuggestion,
}: UseSSEChatOptions): UseSSEChatReturn {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll when messages or streaming text change
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return

    const userMsg: ChatMsg = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]

    setInput('')
    setStreamingText('')

    if (mode === 'direct') {
      // Add user msg + empty assistant placeholder
      setMessages([...newMessages, { role: 'assistant', content: '' }])
    } else {
      // Assist mode: add user msg, streaming text shown separately
      setMessages(newMessages)
    }
    setStreaming(true)

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody(newMessages)),
      })

      if (!res.ok || !res.body) {
        const errorMsg = 'Failed to connect to AI.'
        if (mode === 'direct') {
          setMessages((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: 'assistant', content: errorMsg }
            return copy
          })
        } else {
          setMessages([...newMessages, { role: 'assistant', content: errorMsg }])
        }
        setStreaming(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let finalReply = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()!

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))

            if (mode === 'direct') {
              // Direct: append tokens to last message
              if (evt.t) {
                accumulated += evt.t
                setMessages((prev) => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                  return copy
                })
              }
              if (evt.error) {
                accumulated += `\n\n[Error: ${evt.error}]`
                setMessages((prev) => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { role: 'assistant', content: accumulated }
                  return copy
                })
              }
            } else {
              // Assist: accumulate raw tokens, extract reply from partial JSON
              if (evt.t) {
                accumulated += evt.t
                const partial = extractReplyFromPartial(accumulated)
                if (partial) setStreamingText(partial)
              } else if (evt.done) {
                finalReply = evt.reply || ''
                if (evt.suggestion && onSuggestion) {
                  onSuggestion(evt.suggestion)
                }
              } else if (evt.error) {
                finalReply = `Error: ${evt.error}`
              }
            }
          } catch { /* skip malformed SSE */ }
        }
      }

      // Finalize assist mode: commit the reply as a message
      if (mode === 'assist') {
        const content = finalReply || extractReplyFromPartial(accumulated) || accumulated
        setMessages([...newMessages, { role: 'assistant', content }])
        setStreamingText('')
      }
    } catch {
      const errorMsg = 'Connection error.'
      if (mode === 'direct') {
        setMessages((prev) => {
          const copy = [...prev]
          copy[copy.length - 1] = { role: 'assistant', content: errorMsg }
          return copy
        })
      } else {
        setMessages([...newMessages, { role: 'assistant', content: errorMsg }])
      }
    } finally {
      setStreaming(false)
    }
  }, [input, streaming, messages, endpoint, buildBody, mode, onSuggestion])

  const reset = useCallback(() => {
    setMessages([])
    setInput('')
    setStreamingText('')
    setStreaming(false)
  }, [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault()
        send()
      }
    },
    [send],
  )

  return {
    messages,
    input,
    setInput,
    streaming,
    streamingText,
    send,
    reset,
    scrollRef,
    handleKeyDown,
  }
}
