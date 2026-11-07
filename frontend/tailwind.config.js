/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fff7ed",
          100: "#ffedd5",
          200: "#fed7aa",
          300: "#fdba74",
          400: "#fb923c",
          500: "#f97316", // primary orange
          600: "#ea580c",
          700: "#c2410c",
          800: "#9a3412",
          900: "#7c2d12",
        },
        darkbg: "#121212",
        darkcard: "#1e1e1e",
        darkborder: "#2d2d2d",
      },
      borderRadius: {
        card: "12px",
      },
      boxShadow: {
        solid: "0 2px 8px rgba(0, 0, 0, 0.08)",
        soliddark: "0 2px 8px rgba(0, 0, 0, 0.4)",
      },
    },
  },
  plugins: [],
};

