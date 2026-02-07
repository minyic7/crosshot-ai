import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useListContentsQuery } from '@/store/api'

export function ContentsTable() {
  const [platform, setPlatform] = useState('')
  const { data, isLoading } = useListContentsQuery(
    platform ? { platform } : undefined,
    { pollingInterval: 10000 },
  )

  const contents = data?.contents ?? []

  return (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm font-medium" style={{ color: 'var(--foreground-muted)' }}>Platform:</span>
          {['', 'xhs', 'x'].map((p) => (
            <button
              key={p}
              className={`btn btn-sm ${platform === p ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setPlatform(p)}
            >
              {p || 'All'}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="stack-sm">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="w-full h-12" />
            ))}
          </div>
        ) : (
          <div className="table-compact">
            <div className="table-compact-row" style={{ fontWeight: 600, borderBottom: '2px solid #e5e7eb' }}>
              <span style={{ flex: 0.5 }}>Platform</span>
              <span style={{ flex: 1 }}>URL</span>
              <span style={{ flex: 1 }}>Crawled At</span>
            </div>
            {contents.length > 0 ? (
              contents.map((content) => (
                <div key={content.id} className="table-compact-row">
                  <span style={{ flex: 0.5 }}>
                    <Badge variant="muted">{content.platform}</Badge>
                  </span>
                  <span style={{ flex: 1 }} className="text-sm truncate">
                    {content.source_url}
                  </span>
                  <span style={{ flex: 1 }} className="text-sm">
                    {new Date(content.crawled_at).toLocaleString()}
                  </span>
                </div>
              ))
            ) : (
              <p className="py-4 text-center" style={{ color: 'var(--foreground-subtle)' }}>No contents found</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
