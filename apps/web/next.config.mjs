/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The API base URL is read at *build* time on purpose. Phase 1 has no chat endpoint and
  // no authenticated browser session, so there is nothing to proxy; phase 4 replaces this
  // with a rewrite that forwards the Authorization header server-side.
  env: {
    API_BASE_URL: process.env.API_BASE_URL ?? 'http://localhost:8000',
  },
};

export default nextConfig;