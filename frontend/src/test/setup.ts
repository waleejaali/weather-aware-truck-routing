import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

afterEach(() => cleanup())

// jsdom does not implement scrolling; the app scrolls on page changes.
beforeEach(() => {
  window.scrollTo = vi.fn()
  window.location.hash = ''
})
