import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '../test-utils'
import { renderWithProviders } from '../test-utils'
import ProfilePage from './Profile'
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

const fakeUser = {
  id: '1',
  email: 'alice@example.com',
  username: 'alice',
  subjects_list: ['general', 'math'],
  current_subject: 'general',
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(fakeUser))
    vi.mocked(api.get).mockResolvedValue({ documents: [] })
  })

  it('renders the account details form and subject workspace buttons', async () => {
    renderWithProviders(<ProfilePage />)
    expect(screen.getByPlaceholderText('Your name')).toBeInTheDocument()
    expect(await screen.findByText('general')).toBeInTheDocument()
    expect(screen.getByText('math')).toBeInTheDocument()
  })

  it('renders uploaded documents by filename', async () => {
    vi.mocked(api.get).mockResolvedValue({
      documents: [
        {
          id: 'd1', filename: 'lecture-notes.pdf', file_size: 1024,
          chunks_count: 12, uploaded_at: new Date().toISOString(),
        },
      ],
    })
    renderWithProviders(<ProfilePage />)
    expect(await screen.findByText('lecture-notes.pdf')).toBeInTheDocument()
  })

  it('switches subject workspace when a workspace button is clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(api.patch).mockResolvedValue({ subject: 'math' })
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path === '/auth/me') return Promise.resolve(fakeUser)
      return Promise.resolve({ documents: [] })
    })

    renderWithProviders(<ProfilePage />)
    await screen.findByText('math')
    await user.click(screen.getByText('math'))

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/auth/subject', { subject: 'math' })
    })
  })

  it('rejects a password change when confirmation does not match', async () => {
    // The three password fields share the same placeholder and aren't
    // associated to their <label> via htmlFor/id, so select by order
    // (current, next, confirm) matching the component's own field array.
    const user = userEvent.setup()
    renderWithProviders(<ProfilePage />)

    const [current, next, confirm] = await screen.findAllByPlaceholderText('••••••••')
    await user.type(current, 'oldpass123')
    await user.type(next, 'newpass123')
    await user.type(confirm, 'different123')

    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /update password/i })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalledWith('/auth/change-password', expect.anything())
  })
})
