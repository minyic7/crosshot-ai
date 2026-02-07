import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { useSendChatMessageMutation } from '@/store/api'
import type { ChatMessage } from '@/types/models'

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sendMessage, { isLoading }] = useSendChatMessageMutation()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')

    try {
      const response = await sendMessage({ message: userMessage.content }).unwrap()
      setMessages((prev) => [...prev, response])
    } catch {
      const errorMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Failed to get response. Is the coordinator running?',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMessage])
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="stack" style={{ height: 'calc(100vh - 160px)' }}>
      <div className="flex items-center gap-2">
        <MessageSquare size={20} />
        <h1 className="text-xl font-semibold">Chat with Coordinator</h1>
      </div>

      <Card style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <CardContent style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 0' }}>
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p style={{ color: 'var(--foreground-subtle)' }}>
                  Send a message to start a conversation with the coordinator agent.
                </p>
              </div>
            ) : (
              <div className="stack-sm">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className="glass-card-static"
                      style={{
                        maxWidth: '70%',
                        padding: '0.75rem 1rem',
                        backgroundColor: msg.role === 'user' ? 'var(--teal)' : undefined,
                        color: msg.role === 'user' ? '#fff' : undefined,
                      }}
                    >
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      <p
                        className="text-xs mt-1"
                        style={{ opacity: 0.6 }}
                      >
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input */}
          <div className="flex gap-2" style={{ borderTop: '1px solid #e5e7eb', paddingTop: '1rem' }}>
            <textarea
              className="form-textarea"
              placeholder="Type a message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              style={{ resize: 'none', flex: 1 }}
            />
            <Button onClick={handleSend} disabled={isLoading || !input.trim()}>
              <Send size={16} />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
