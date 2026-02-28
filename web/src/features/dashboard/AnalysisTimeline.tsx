import { useState } from 'react'
import { ChevronDown, ChevronRight, Clock, FileText, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Markdown } from '@/components/ui/Markdown'
import { useGetTopicPeriodsQuery, useGetUserPeriodsQuery } from '@/store/api'
import { useTimezone } from '@/hooks/useTimezone'
import type { AnalysisPeriod, TopicInsight } from '@/types/models'

function fmtNum(n: unknown): string {
  if (n == null) return '-'
  const v = Number(n)
  if (isNaN(v)) return '-'
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

function normalizeInsights(data: Record<string, unknown> | null): TopicInsight[] {
  if (!data) return []
  const result: TopicInsight[] = []
  const insights = data.insights
  if (Array.isArray(insights)) {
    for (const item of insights) {
      if (typeof item === 'object' && item !== null && 'text' in item) {
        const i = item as { text: string; sentiment?: string }
        result.push({ text: i.text, sentiment: (i.sentiment as TopicInsight['sentiment']) ?? 'neutral' })
      } else if (typeof item === 'string') {
        result.push({ text: item, sentiment: 'neutral' })
      }
    }
  }
  return result
}

function DeltaChip({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null
  const v = Number(value)
  if (isNaN(v) || v === 0) return null
  const isPos = v > 0
  return (
    <span className={`timeline-delta-chip ${isPos ? 'positive' : 'negative'}`}>
      {label} {isPos ? '+' : ''}{fmtNum(v)}
    </span>
  )
}

function PeriodNode({ period, isLatest, fmt }: { period: AnalysisPeriod; isLatest: boolean; fmt: (s: string | null) => string }) {
  const [expanded, setExpanded] = useState(false)
  const insights = normalizeInsights(period.insights)
  const delta = period.metrics_delta as Record<string, unknown> | null

  return (
    <div className={`timeline-node ${isLatest ? 'latest' : ''}`}>
      <div className={`timeline-dot ${isLatest ? 'active' : ''}`} />
      <button className="timeline-card" onClick={() => setExpanded(!expanded)}>
        <div className="timeline-card-header">
          <span className="timeline-period-num">#{period.period_number}</span>
          <span className="timeline-period-date">
            {fmt(period.period_start)} — {fmt(period.period_end)}
          </span>
          <span className="timeline-content-count">
            <FileText size={10} /> {period.content_count}
          </span>
          {expanded ? <ChevronDown size={14} className="timeline-chevron" /> : <ChevronRight size={14} className="timeline-chevron" />}
        </div>

        {period.summary_short && !expanded && (
          <div className="timeline-card-summary-short">{period.summary_short}</div>
        )}

        {delta && (
          <div className="timeline-card-deltas">
            <DeltaChip label="posts" value={delta.total_posts} />
            <DeltaChip label="likes" value={delta.total_likes} />
            <DeltaChip label="views" value={delta.total_views} />
            <DeltaChip label="retweets" value={delta.total_retweets} />
            <DeltaChip label="replies" value={delta.total_replies} />
          </div>
        )}
      </button>

      {expanded && (
        <div className="timeline-expanded">
          {period.summary && (
            <div className="timeline-full-summary">
              <Markdown>{period.summary}</Markdown>
            </div>
          )}
          {insights.length > 0 && (
            <div className="summary-insights" style={{ marginTop: 12 }}>
              {insights.map((insight, i) => (
                <div key={i} className={`summary-insight ${insight.sentiment}`}>
                  {insight.sentiment === 'positive' ? <TrendingUp size={12} /> : insight.sentiment === 'negative' ? <TrendingDown size={12} /> : <Minus size={12} />}
                  <span>{insight.text}</span>
                </div>
              ))}
            </div>
          )}
          {period.quality_score != null && (
            <div className="timeline-quality">
              Quality: {period.quality_score}/10
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function AnalysisTimeline({ entityType, entityId }: { entityType: 'topic' | 'user'; entityId: string }) {
  const topicResult = useGetTopicPeriodsQuery(entityId, { skip: entityType !== 'topic' })
  const userResult = useGetUserPeriodsQuery(entityId, { skip: entityType !== 'user' })
  const { fmt } = useTimezone()

  const { data, isLoading } = entityType === 'topic' ? topicResult : userResult

  if (isLoading) {
    return (
      <Card>
        <CardContent style={{ padding: 16 }}>
          <Skeleton className="w-48 h-4" />
          <div style={{ marginTop: 16 }}><Skeleton className="w-full h-20" /></div>
        </CardContent>
      </Card>
    )
  }

  if (!data?.periods?.length) return null

  const periods = data.periods

  return (
    <Card>
      <CardContent style={{ padding: 0 }}>
        <CardHeader style={{ padding: '16px 16px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={13} style={{ color: 'var(--ink-3)' }} />
            <CardDescription>Analysis Timeline ({periods.length} periods)</CardDescription>
          </div>
        </CardHeader>
        <div className="analysis-timeline">
          <div className="timeline-line" />
          {periods.map((period, i) => (
            <PeriodNode key={period.id} period={period} isLatest={i === 0} fmt={fmt} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
