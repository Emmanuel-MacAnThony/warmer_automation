// Light mode temporarily disabled — dark only
// import { useEffect, useState } from 'react'
// type Theme = 'dark' | 'light'
// export function useTheme() {
//   const [theme, setTheme] = useState<Theme>(() => {
//     const stored = localStorage.getItem('theme') as Theme | null
//     if (stored) return stored
//     return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
//   })
//   useEffect(() => {
//     const root = document.documentElement
//     if (theme === 'dark') { root.classList.add('dark') } else { root.classList.remove('dark') }
//     localStorage.setItem('theme', theme)
//   }, [theme])
//   const toggle = () => setTheme(t => t === 'dark' ? 'light' : 'dark')
//   return { theme, toggle }
// }

export function useTheme() {
  return { theme: 'dark' as const, toggle: () => {} }
}
