import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn('skeleton', className)} />
}

export function SkeletonText({ className }: SkeletonProps) {
  return <div className={cn('skeleton skeleton-text', className)} />
}
