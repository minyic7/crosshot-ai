import { cn } from '@/lib/utils'

interface StatusDotProps {
  status: 'running' | 'stopped' | 'error'
  className?: string
}

export function StatusDot({ status, className }: StatusDotProps) {
  const stateClass = status === 'running' ? 'online' : status === 'error' ? 'error' : 'offline'
  return <span className={cn('status-dot', stateClass, className)} />
}
