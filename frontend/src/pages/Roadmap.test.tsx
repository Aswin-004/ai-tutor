import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '../test-utils'
import { renderWithProviders } from '../test-utils'
import RoadmapPage from './Roadmap'
import { api } from '../lib/api'

vi.mock('../lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('RoadmapPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the empty state when no roadmap exists', async () => {
    vi.mocked(api.get).mockResolvedValue({ roadmap: null })
    renderWithProviders(<RoadmapPage />)
    expect(await screen.findByText('No roadmap yet')).toBeInTheDocument()
  })

  it('renders a generated step using the canonical schema (title/description/objectives/time/difficulty/activities)', async () => {
    // Regression guard for the Sprint 1 bug: backend used to send
    // {module, topic, ...}, frontend expected {step, title, description,
    // topics, resources, priority} - zero field overlap, cards rendered empty.
    vi.mocked(api.get).mockResolvedValue({
      roadmap: [{
        step: 1,
        title: 'Intro to Recursion',
        description: 'Learn the fundamentals of recursive functions.',
        objectives: ['Understand base cases', 'Trace call stacks'],
        time: '2 hours',
        difficulty: 'Beginner',
        activities: ['Write a factorial function'],
      }],
    })
    renderWithProviders(<RoadmapPage />)

    expect(await screen.findByText('Intro to Recursion')).toBeInTheDocument()
    expect(screen.getByText('Learn the fundamentals of recursive functions.')).toBeInTheDocument()
    expect(screen.getByText('Understand base cases')).toBeInTheDocument()
    expect(screen.getByText('Trace call stacks')).toBeInTheDocument()
    expect(screen.getByText(/2 hours/)).toBeInTheDocument()
    expect(screen.getByText('Beginner')).toBeInTheDocument()
    expect(screen.getByText('Write a factorial function')).toBeInTheDocument()
  })

  it('triggers roadmap generation when "Generate roadmap" is clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ roadmap: null })
    vi.mocked(api.post).mockResolvedValue({ roadmap: [] })

    renderWithProviders(<RoadmapPage />)
    const btn = await screen.findByRole('button', { name: /generate roadmap/i })
    await user.click(btn)

    expect(api.post).toHaveBeenCalledWith('/generate_roadmap', {})
  })
})
