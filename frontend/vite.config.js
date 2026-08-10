import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Fail if 5173 is taken instead of quietly moving to 5174. The backend
    // allows CORS from this exact origin, so a silent port change turns into a
    // rejected preflight and a "Failed to fetch" in the UI -- while the backend
    // log shows healthy 200s. Refusing to start says what is wrong immediately.
    strictPort: true,
  },
});
