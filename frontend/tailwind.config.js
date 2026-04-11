/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { primary: '#000000', card: '#111111', subtle: '#080808' },
        accent: { sand: '#F2C48D', gold: '#D4AF37' },
        success: '#00C853',
        alert: '#FF5252',
        border: { DEFAULT: '#222222', hover: '#333333' },
        text: { primary: '#FFFFFF', secondary: '#B0B0B0', muted: '#666666' },
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      borderRadius: { '2xl': '16px' },
    },
  },
  plugins: [],
};
