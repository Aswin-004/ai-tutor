import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// vitest.config's `test` block doesn't set `globals: true`, so Testing
// Library's own auto-cleanup (which detects a *global* afterEach) never
// registers - without this, every render in a test file accumulates in
// the same jsdom document and later queries in the same file start
// matching multiple stale elements from earlier tests.
afterEach(() => {
  cleanup()
})

// jsdom doesn't implement scrollIntoView; Chat.tsx calls it on every
// history update to auto-scroll to the newest message.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

// jsdom doesn't implement these, and Framer Motion (used across every page
// in this app) touches them even for simple mount/unmount animations.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
