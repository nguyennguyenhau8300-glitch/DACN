import { createRequire } from 'node:module';

const require = createRequire(new URL('../DACN/web_dashboard/package.json', import.meta.url));
export const { defineConfig, test, expect } = require('@playwright/test');
