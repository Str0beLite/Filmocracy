import { networkInterfaces } from 'node:os';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const PORT = 5173;

// The laptop's Wi-Fi address, so the TV's QR code works on phones even when
// the TV page itself is open on localhost.
function lanOrigin() {
  for (const list of Object.values(networkInterfaces())) {
    for (const net of list ?? []) {
      if (net.family === 'IPv4' && !net.internal && !net.address.startsWith('169.254.')) {
        return `http://${net.address}:${PORT}`;
      }
    }
  }
  return '';
}

// In dev, /api goes to the backend on this laptop (sockets too), so phones on
// the Wi-Fi only need to reach this one address. VITE_API_URL overrides it.
const BACKEND = process.env.TANDEM_BACKEND ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  define: { __LAN_ORIGIN__: JSON.stringify(lanOrigin()) },
  server: {
    port: PORT,
    strictPort: true,
    // Cloudflare quick tunnels give phones an https address, which Google sign-in requires.
    allowedHosts: ['.trycloudflare.com'],
    proxy: { '/api': { target: BACKEND, ws: true, rewrite: (path) => path.replace(/^\/api/, '') } },
  },
});
