/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Ensure dark mode is class-based to allow toggling
  theme: {
    extend: {
      colors: {
        secondary: {
          100: '#E8F5FE',
          200: '#BDEDFF',
          300: '#79D3FF',
          400: '#38B2FF',
          500: '#009EFF',
          600: '#007ECC',
          700: '#005C99',
          800: '#003D66',
          900: '#002033'
        }
      }
    }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
};