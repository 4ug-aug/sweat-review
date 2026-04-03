import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { TooltipProvider } from "@/components/ui/tooltip"
import { Analytics } from "@vercel/analytics/react"

// Theme-aware favicon switcher
function initializeFavicon() {
  const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')

  function updateFavicon() {
    if (!favicon) return

    const isDark = document.documentElement.classList.contains('dark')
    favicon.href = isDark ? '/sweat-review.svg' : '/sweat-review-light.svg'
  }

  // Set initial favicon
  updateFavicon()

  // Listen for theme changes via MutationObserver on html class
  const observer = new MutationObserver(() => {
    updateFavicon()
  })

  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  })
}

initializeFavicon()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TooltipProvider>
      <App />
    </TooltipProvider>
    <Analytics />
  </StrictMode>,
)
