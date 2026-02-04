import { useState, useEffect, useRef, useCallback } from "react"

interface UsePollingApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function usePollingApi<T>(
  url: string,
  intervalMs: number = 5000
): UsePollingApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<number | null>(null)

  const fetchData = useCallback(() => {
    if (!url || intervalMs <= 0) return

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((json) => {
        setData(json)
        setLoading(false)
        setError(null)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [url, intervalMs])

  useEffect(() => {
    if (!url || intervalMs <= 0) {
      setLoading(false)
      return
    }

    fetchData()
    intervalRef.current = window.setInterval(fetchData, intervalMs)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchData, intervalMs, url])

  return { data, loading, error, refetch: fetchData }
}
