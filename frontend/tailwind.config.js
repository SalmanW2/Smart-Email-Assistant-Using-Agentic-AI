/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Yahan se deep dark mode control hoga
  theme: {
    extend: {
      // Future mein agar custom colors chahiye honge toh yahan add karenge, bina plugins ke
    },
  },
  plugins: [], // Extra global plugins hata diye hain taake form inputs kharab na hon
}