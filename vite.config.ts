import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
    const apiPort = process.env.VITE_API_PORT ?? process.env.API_PORT ?? '8000';
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          '/api': `http://127.0.0.1:${apiPort}`,
          '/v1': `http://127.0.0.1:${apiPort}`,
        },
      },
      plugins: [react()],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, 'src'),
        }
      }
    };
});
