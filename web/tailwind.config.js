/** Every colour comes from a design token defined once in src/index.css. */
const token = (name) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        ink: { DEFAULT: token("ink"), 2: token("ink-2"), 3: token("ink-3") },
        line: token("line"),
        fill: { DEFAULT: token("fill"), 2: token("fill-2") },
        accent: { DEFAULT: token("accent"), ink: token("accent-ink"), tint: token("accent-tint") },
        red: { DEFAULT: token("red"), tint: token("red-tint") },
        green: { DEFAULT: token("green"), tint: token("green-tint") },
        amber: { DEFAULT: token("amber"), tint: token("amber-tint") },
      },
      borderRadius: { DEFAULT: "var(--radius)", sm: "6px", lg: "14px", xl: "18px", "2xl": "22px" },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Inter Tight", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["13px", "18px"],
        base: ["15px", "22px"],
        md: ["17px", "24px"],
        lg: ["21px", "27px"],
        xl: ["28px", "32px"],
        "2xl": ["40px", "42px"],
        "3xl": ["56px", "56px"],
      },
    },
  },
};
