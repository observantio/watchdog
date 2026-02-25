import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext({
  theme: 'dark',
  toggleTheme: () => {},
})

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    // Check localStorage first
    const savedTheme = localStorage.getItem('theme')
    if (savedTheme === 'dark' || savedTheme === 'light') return savedTheme

    // Check system preference
    if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }

    return 'light' // Default to light theme
  })

  useEffect(() => {
    const root = document.documentElement
    const body = document.body

    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }

    root.setAttribute('data-theme', theme)
    body.setAttribute('data-theme', theme)

    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}
