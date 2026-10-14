/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0f17',
          850: '#111724',
          800: '#151d2e',
          750: '#1b253b',
          700: '#222f49',
          600: '#334466',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Consolas', 'Menlo', 'Monaco', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
