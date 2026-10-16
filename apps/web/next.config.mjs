const API = process.env.API_URL ?? "http://localhost:8010";

/** @type {import('next').NextConfig} */
export default {
  // same-origin: браузер ходить на /api/*, Next проксіює на FastAPI (cookies без CORS)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
