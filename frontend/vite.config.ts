import { networkInterfaces } from 'node:os';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { mockBackend } from './mock-backend';

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

export default defineConfig({
  plugins: [react(), mockBackend()],
  define: { __LAN_ORIGIN__: JSON.stringify(lanOrigin()) },
  server: { port: PORT, strictPort: true },
});
