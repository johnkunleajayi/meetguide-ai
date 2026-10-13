import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Avoid native realpath failures for Windows OneDrive checkouts in restricted environments.
  resolve: { preserveSymlinks: true },
});
