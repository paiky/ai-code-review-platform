import { build } from 'vite';

await build({
  root: process.cwd(),
  configFile: 'vite.config.js'
});
