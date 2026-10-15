import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'*.spec.js',fullyParallel:false,workers:1,timeout:60000,retries:0,reporter:'list',use:{baseURL:process.env.E2E_BASE_URL||'http://127.0.0.1:5173/dashboard/',viewport:{width:1440,height:1000},trace:'retain-on-failure',screenshot:'only-on-failure'}});
