import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '../test-utils'
import { renderWithProviders } from '../test-utils'
import AuthPage from './Auth'
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

describe('AuthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders the login form by default', () => {
    renderWithProviders(<AuthPage />, { route: '/auth' })
    expect(screen.getByPlaceholderText('your_username')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('logs in successfully and persists the token', async () => {
    const user = userEvent.setup()
    vi.mocked(api.post).mockResolvedValueOnce({
      access_token: 'fake-token',
      token_type: 'bearer',
      user: {
        id: '1', email: 'alice@example.com', username: 'alice',
        subjects_list: ['general'], current_subject: 'general',
      },
    })

    renderWithProviders(<AuthPage />, { route: '/auth' })

    await user.type(screen.getByPlaceholderText('your_username'), 'alice')
    await user.type(screen.getByPlaceholderText('••••••••'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/login', {
        username: 'alice',
        password: 'password123',
      })
    })
    await waitFor(() => {
      expect(localStorage.getItem('token')).toBe('fake-token')
    })
  })

  it('shows an error message on failed login instead of navigating', async () => {
    const user = userEvent.setup()
    vi.mocked(api.post).mockRejectedValueOnce(new Error('Invalid username or password'))

    renderWithProviders(<AuthPage />, { route: '/auth' })

    await user.type(screen.getByPlaceholderText('your_username'), 'alice')
    await user.type(screen.getByPlaceholderText('••••••••'), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('switches to the register tab and submits registration', async () => {
    const user = userEvent.setup()
    vi.mocked(api.post).mockResolvedValueOnce({
      access_token: 'new-token',
      token_type: 'bearer',
      user: {
        id: '2', email: 'jane@example.com', username: 'jane_doe',
        subjects_list: ['general'], current_subject: 'general',
      },
    })

    renderWithProviders(<AuthPage />, { route: '/auth' })

    await user.click(screen.getByRole('button', { name: /^register$/i }))
    // AnimatePresence (mode="wait") animates the login form out before the
    // register form mounts, so the fields aren't there synchronously.
    await user.type(await screen.findByPlaceholderText('jane@example.com'), 'jane@example.com')
    await user.type(screen.getByPlaceholderText('jane_doe'), 'jane_doe')
    await user.type(screen.getByPlaceholderText('min. 8 characters'), 'password123')
    await user.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/register', {
        email: 'jane@example.com',
        username: 'jane_doe',
        password: 'password123',
        full_name: undefined,
      })
    })
  })
})
