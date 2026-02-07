import { useState } from 'react'
import { Send } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { useCreateJobMutation } from '@/store/api'

export function CreateTaskForm() {
  const [description, setDescription] = useState('')
  const [createJob, { isLoading, isSuccess, data }] = useCreateJobMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!description.trim()) return
    await createJob({ description: description.trim() })
    setDescription('')
  }

  return (
    <Card>
      <CardContent>
        <CardHeader>
          <CardTitle>Publish New Task</CardTitle>
        </CardHeader>
        <form onSubmit={handleSubmit} className="stack-sm" style={{ marginTop: '1rem' }}>
          <div className="form-group">
            <label htmlFor="description" className="form-label">Description</label>
            <textarea
              id="description"
              className="form-textarea"
              placeholder="Describe what you want the agents to do..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={isLoading || !description.trim()}>
              <Send size={14} />
              {isLoading ? 'Submitting...' : 'Submit'}
            </Button>
            {isSuccess && data && (
              <span className="text-sm" style={{ color: 'var(--success)' }}>
                Job created: {data.job_id.slice(0, 8)}... ({data.tasks_created} tasks)
              </span>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
