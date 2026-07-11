/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#131417',
        foreground: '#ebecef',
        card: '#1c1d22',
        secondary: '#24262c',
        muted: '#8f929c',
        primary: { DEFAULT: '#f2a33c', foreground: '#2b1e08' },
        destructive: '#e05d47',
        line: 'rgba(255,255,255,0.08)',
        field: 'rgba(255,255,255,0.1)'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif']
      },
      keyframes: {
        'float-bob': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' }
        },
        'fade-in-up': {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to: { opacity: '1', transform: 'translateY(0)' }
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '0.7', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.08)' }
        }
      },
      animation: {
        'float-bob': 'float-bob 5s ease-in-out infinite',
        'fade-in-up': 'fade-in-up 0.7s ease-out both',
        'glow-pulse': 'glow-pulse 6s ease-in-out infinite'
      }
    }
  },
  plugins: [],
}
