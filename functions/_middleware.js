// Proksi API untuk Cloudflare Pages (opsional).
//
// Dipakai HANYA jika frontend PWA di-host terpisah dari backend Render.
// Tujuannya menjaga frontend dan API tetap satu origin, karena cookie sesi
// CatatKas memakai HttpOnly + SameSite=Lax dan tidak akan terkirim lintas situs.
//
// Konfigurasi Cloudflare Pages:
//   - Build command   : (kosong)
//   - Output directory: pwa
//   - Environment var : CATATKAS_API_ORIGIN = https://<nama-layanan>.onrender.com
//
// File statis (index.html, app.js, dst.) tetap dilayani Pages lewat next().

const API_ROUTE_PREFIXES = ["/auth", "/transactions", "/extract", "/health"];
const DEFAULT_API_ORIGIN = "https://catatkas.onrender.com";

function isApiRequest(pathname) {
  return API_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);

  if (!isApiRequest(url.pathname)) {
    return next();
  }

  const origin = (env.CATATKAS_API_ORIGIN || DEFAULT_API_ORIGIN).replace(/\/+$/, "");
  const target = `${origin}${url.pathname}${url.search}`;

  // Request baru membawa method, header, dan body asli; Host mengikuti target.
  return fetch(new Request(target, request));
}
