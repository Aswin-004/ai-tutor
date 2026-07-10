import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '../test-utils'
import { renderWithProviders } from '../test-utils'
import ChatPage from './Chat'
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

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the empty state when there is no chat history', async () => {
    vi.mocked(api.get).mockResolvedValue({ history: [] })
    renderWithProviders(<ChatPage />)
    expect(await screen.findByText('Start a conversation')).toBeInTheDocument()
  })

  it('renders persisted chat history', async () => {
    vi.mocked(api.get).mockResolvedValue({
      history: [
        { role: 'user', message: 'Explain recursion', created_at: new Date().toISOString() },
        { role: 'assistant', message: 'Recursion is when a function calls itself.', created_at: new Date().toISOString() },
      ],
    })
    renderWithProviders(<ChatPage />)
    expect(await screen.findByText('Explain recursion')).toBeInTheDocument()
    expect(screen.getByText('Recursion is when a function calls itself.')).toBeInTheDocument()
  })

  it('sends a message (optimistic bubble, then the AI response) and posts to /chat', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ history: [] })
    vi.mocked(api.post).mockResolvedValue({
      response: 'Sure, let me explain recursion.',
      emotion: 'neutral',
      videos: [],
    })

    renderWithProviders(<ChatPage />)
    await screen.findByText('Start a conversation')

    const textarea = screen.getByPlaceholderText('Ask a question…')
    await user.type(textarea, 'Explain recursion{Enter}')

    // Optimistic user bubble appears immediately, before the mutation resolves.
    expect(await screen.findByText('Explain recursion')).toBeInTheDocument()
    // AI response appears once the mutation resolves.
    expect(await screen.findByText('Sure, let me explain recursion.')).toBeInTheDocument()

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/chat', { message: 'Explain recursion' })
    })
  })

  it('removes the optimistic message if the send fails', async () => {
    // The optimistic add (onMutate) and the rollback (onError) can land in
    // the same render pass when the mock rejects near-instantly, so the
    // "appears" moment isn't reliably observable here - only assert the
    // end state: the failed message is gone and the input is usable again.
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({ history: [] })
    vi.mocked(api.post).mockRejectedValue(new Error('Network error'))

    renderWithProviders(<ChatPage />)
    await screen.findByText('Start a conversation')

    const textarea = screen.getByPlaceholderText('Ask a question…')
    await user.type(textarea, 'Explain recursion{Enter}')

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/chat', { message: 'Explain recursion' })
    })
    await waitFor(() => {
      expect(screen.queryByText('Explain recursion')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Start a conversation')).toBeInTheDocument()
  })
})
