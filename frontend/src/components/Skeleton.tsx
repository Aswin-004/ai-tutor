import { cn } from '../lib/cn'

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={cn('shimmer rounded-lg bg-white/5', className)} />
  )
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card space-y-3">
      <Skeleton className="h-4 w-2/3" />
      {Array.from({ length: lines - 1 }).map((_, i) => (
        <Skeleton key={i} className={cn('h-3', i === lines - 2 ? 'w-1/2' : 'w-full')} />
      ))}
    </div>
  )
}

export function SkeletonStat() {
  return (
    <div className="card space-y-2">
      <Skeleton className="h-3 w-1/2" />
      <Skeleton className="h-8 w-2/3" />
    </div>
  )
}
