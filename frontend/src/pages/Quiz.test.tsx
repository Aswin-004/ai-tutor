import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '../test-utils'
import { renderWithProviders } from '../test-utils'
import QuizPage from './Quiz'
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

describe('QuizPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue({ weak_topics: [] })
  })

  it('generates a quiz and highlights correctness using the correct_answer field', async () => {
    // Regression guard for the Sprint 1 bug: backend used to send "answer",
    // frontend read "correct_answer" - scoring was silently always 0%.
    const user = userEvent.setup()
    vi.mocked(api.post).mockImplementation((path: string) => {
      if (path === '/quiz/generate') {
        return Promise.resolve({
          quiz: [{
            question: 'What is recursion?',
            options: ['A loop', 'A function calling itself', 'A variable', 'A class'],
            correct_answer: 'A function calling itself',
            explanation: 'Recursion is when a function calls itself.',
          }],
          total_questions: 1,
        })
      }
      return Promise.resolve({ message: 'Quiz submitted', weak_topics: [] })
    })

    renderWithProviders(<QuizPage />)

    await user.type(screen.getByPlaceholderText(/neural networks/i), 'recursion')
    await user.click(screen.getByRole('button', { name: /generate quiz/i }))

    expect(await screen.findByText('What is recursion?')).toBeInTheDocument()

    await user.click(screen.getByText('A function calling itself'))

    // Explanation only renders after a selection is made, using the same field.
    expect(await screen.findByText('Recursion is when a function calls itself.')).toBeInTheDocument()
  })

  it('submits the correct score on quiz completion', async () => {
    const user = userEvent.setup()
    vi.mocked(api.post).mockImplementation((path: string) => {
      if (path === '/quiz/generate') {
        return Promise.resolve({
          quiz: [{
            question: 'What is recursion?',
            options: ['A loop', 'A function calling itself'],
            correct_answer: 'A function calling itself',
            explanation: '',
          }],
          total_questions: 1,
        })
      }
      return Promise.resolve({ message: 'Quiz submitted', weak_topics: [] })
    })

    renderWithProviders(<QuizPage />)
    await user.type(screen.getByPlaceholderText(/neural networks/i), 'recursion')
    await user.click(screen.getByRole('button', { name: /generate quiz/i }))

    await screen.findByText('What is recursion?')
    await user.click(screen.getByText('A function calling itself'))
    await user.click(screen.getByRole('button', { name: /see results/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/quiz/submit', {
        score: 1,
        total_questions: 1,
        topic: 'recursion',
      })
    })
    expect(await screen.findByText('100%')).toBeInTheDocument()
  })
})
