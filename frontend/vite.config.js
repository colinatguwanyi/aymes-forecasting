import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
    plugins: [vue(), tailwindcss()],
    resolve: {
        alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
                // Large CSV/XLSX uploads finish quickly in the browser, then the API stages millions of
                // rows before responding — the default proxy idle timeout drops the connection otherwise.
                timeout: 3600000,
                proxyTimeout: 3600000,
            },
            '/docs': { target: 'http://127.0.0.1:8000', changeOrigin: true },
            '/openapi.json': { target: 'http://127.0.0.1:8000', changeOrigin: true },
        },
    },
});
