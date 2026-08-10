import { build } from 'vite';
import react from '@vitejs/plugin-react';

await build({
  root: process.cwd(),
  configFile: false,
  plugins: [react()]
});
