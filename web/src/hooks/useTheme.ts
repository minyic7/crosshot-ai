import { useState, useEffect, useCallback } from 'react'

type Theme = 'light' | 'dark'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('crosshot-theme') as Theme | null
    return saved ?? 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('crosshot-theme', theme)
  }, [theme])

  const toggle = useCallback(() => {
    document.documentElement.classList.add('theme-transitioning')
    setTheme((t) => (t === 'light' ? 'dark' : 'light'))
    setTimeout(() => document.documentElement.classList.remove('theme-transitioning'), 450)
  }, [])

  return { theme, toggle }
}
