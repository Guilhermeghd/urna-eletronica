"use strict";
/* Service worker da urna. Só guarda a "casca" do app (tela, CSS, JS, ícones) para abrir mais rápido
   e mostrar a tela de "sem conexão" no lugar de um erro do navegador.
   Nunca guarda /api: votos e resultados sempre vão direto ao servidor. */
const CACHE = "urna-v1";
const CASCA = ["/", "/style.css", "/app.js", "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/admin" || url.pathname === "/admin.js") return;
  // rede primeiro (sempre a versão nova); se estiver sem internet, usa a cópia guardada
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) { const cp = res.clone(); caches.open(CACHE).then(c => c.put(req, cp)); }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match("/")))
  );
});
