import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

export type TzOption = 'Australia/Sydney' | 'Asia/Shanghai'

const TZ_OPTIONS: { value: TzOption; label: string }[] = [
  { value: 'Australia/Sydney', label: 'Sydney' },
  { value: 'Asia/Shanghai', label: 'Beijing' },
]

interface TzCtx {
  tz: TzOption
  tzLabel: string
  options: typeof TZ_OPTIONS
  setTz: (tz: TzOption) => void
  fmt: (dateStr: string | null) => string
  fmtRelative: (dateStr: string | null) => string
}

const TimezoneContext = createContext<TzCtx | null>(null)

export function TimezoneProvider({ children }: { children: ReactNode }) {
  const [tz, setTzState] = useState<TzOption>(() => {
    const saved = localStorage.getItem('crosshot-tz') as TzOption | null
    return saved ?? 'Australia/Sydney'
  })

  const setTz = useCallback((val: TzOption) => {
    setTzState(val)
    localStorage.setItem('crosshot-tz', val)
  }, [])

  const fmt = useCallback((dateStr: string | null): string => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString('en-AU', { timeZone: tz, hour12: false })
  }, [tz])

  const fmtRelative = useCallback((dateStr: string | null): string => {
    if (!dateStr) return 'Never'
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60_000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
  }, [])

  const tzLabel = TZ_OPTIONS.find((o) => o.value === tz)?.label ?? tz

  return (
    <TimezoneContext.Provider value={{ tz, tzLabel, options: TZ_OPTIONS, setTz, fmt, fmtRelative }}>
      {children}
    </TimezoneContext.Provider>
  )
}

export function useTimezone() {
  const ctx = useContext(TimezoneContext)
  if (!ctx) throw new Error('useTimezone must be used within TimezoneProvider')
  return ctx
}
