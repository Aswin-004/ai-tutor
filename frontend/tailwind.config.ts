import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#070d1a',
        surface: '#0d1526',
        's2': '#111827',
        accent: '#818cf8',
        'accent-dim': 'rgba(129,140,248,0.12)',
        violet: '#a78bfa',
        cyan: '#67e8f9',
        success: '#34d399',
        warning: '#fbbf24',
        danger: '#f87171',
        border: 'rgba(255,255,255,0.07)',
        'text-base': '#e2e8f0',
        'text-muted': '#94a3b8',
        'text-subtle': '#475569',
      },
      fontFamily: {
        display: ['Outfit', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backgroundImage: {
        'aurora': 'radial-gradient(ellipse 80% 50% at 20% -10%, rgba(129,140,248,0.18) 0%, transparent 60%), radial-gradient(ellipse 60% 40% at 80% 110%, rgba(167,139,250,0.12) 0%, transparent 60%)',
        'aurora-card': 'linear-gradient(135deg, rgba(129,140,248,0.06) 0%, rgba(167,139,250,0.03) 100%)',
        'accent-gradient': 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
      },
      boxShadow: {
        'glass': '0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)',
        'accent-glow': '0 0 20px rgba(129,140,248,0.3)',
        'card': '0 2px 16px rgba(0,0,0,0.3)',
      },
      animation: {
        'fade-up': 'fadeUp 0.4s cubic-bezier(0.16,1,0.3,1)',
        'fade-in': 'fadeIn 0.3s ease',
        'shimmer': 'shimmer 1.8s infinite',
        'aurora-pulse': 'auroraPulse 8s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        auroraPulse: {
          '0%, 100%': { opacity: '0.6' },
          '50%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
