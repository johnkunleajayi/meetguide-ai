import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { preserveSymlinks: true },
  test: { environment: "jsdom", include: ["tests/**/*.test.tsx"] },
});
