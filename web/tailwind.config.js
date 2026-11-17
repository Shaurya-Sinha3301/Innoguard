/** Every colour comes from a design token defined once in src/index.css. */
const token = (name) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        ink: { DEFAULT: token("ink"), 2: token("ink-2"), 3: token("ink-3") },
        line: token("line"),
        fill: { DEFAULT: token("fill"), 2: token("fill-2") },
        red: { DEFAULT: token("red"), tint: token("red-tint") },
        green: { DEFAULT: token("green"), tint: token("green-tint") },
        amber: { DEFAULT: token("amber"), tint: token("amber-tint") },
      },
      borderRadius: { DEFAULT: "var(--radius)", sm: "2px" },
      fontFamily: {
        sans: ["Barlow", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["13px", "18px"],
        base: ["14px", "20px"],
        md: ["16px", "22px"],
        lg: ["20px", "26px"],
        xl: ["24px", "30px"],
      },
    },
  },
};
