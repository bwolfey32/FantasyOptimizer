/* Shader effects: decoration drawn on WebGPU with the shaders library (shaders.com, MIT).
   Three places use it: the weekly weather report's game cards and the app's Research → Weather table (rain, snow,
   wind, fog or sun behind each open-air game, from the same forecast as the words beside it), and the welcome screen's
   four "add your team" cards (a slow gradient in each card's colour, under a glass lens). Each canvas sits behind the
   content and fades in once it has drawn; the CSS look is underneath, so a browser without WebGPU, a failed load or
   offline just shows that.
   Callers check fxOk() before importing this file, so nothing loads for reduced motion or a browser without WebGPU.
   The library is one pinned file from jsdelivr (about 700 KB compressed), checked against its hash before it runs, and
   only fetched when a page has something to draw. Its telemetry (frame-rate samples sent to shaders.com) is off. */
const LIB = { src: 'https://cdn.jsdelivr.net/npm/shaders@4.0.0/dist/js/bundle.js', sri: 'sha384-VDjIeOVAcnhq9MDIGMkbO6OLD5w+pfUpRpIJ8Pfv/f2uuM2o0vmPvMrkvEOnuy0b' };
export const fxOk = () => !!navigator.gpu && !matchMedia('(prefers-reduced-motion: reduce)').matches;

let lib = null, gpu = null;
// fetch() can check a hash where import() can't, so the checked file is imported from a blob URL
function shaders() {
  return lib ||= fetch(LIB.src, { integrity: LIB.sri, mode: 'cors', credentials: 'omit' })
    .then(r => { if (!r.ok) throw new Error(`shaders: ${r.status}`); return r.blob(); })
    .then(b => { const u = URL.createObjectURL(new Blob([b], { type: 'text/javascript' })); return import(u).finally(() => URL.revokeObjectURL(u)); })
    .catch(e => { lib = null; throw e; });
}
// One GPU device shared by every canvas on the page: pipelines compile once and the cards start faster
async function mount(canvas, components) {
  const S = await shaders();
  gpu ||= S.createSharedDevice().catch(() => null);
  const dev = await gpu;
  return S.createShader(canvas, { components }, { disableTelemetry: true, ...(dev ? { gpu: dev } : {}),
    onReady: () => canvas.classList.add('on'), onError: () => canvas.classList.remove('on') });
}
const fxCanvas = () => { const c = document.createElement('canvas'); c.className = 'fx'; c.setAttribute('aria-hidden', 'true'); return c; };

/* Canvases kept across the app's renders. The app rebuilds its HTML on every render, so each effect's canvas is kept by
   key and moved into the new element (a canvas keeps its GPU context when it moves); a new signature (the forecast
   changed, say) starts it over. An item is { key, host (where the canvas goes), watch (what to follow for size, the
   host by default), sig, cls }; place(fx) fits a canvas to its item, after each sync and when the watched element
   resizes. Keys missing from a sync are paused while keep is set and released when it isn't. */
function keeper(layers, place) {
  const kept = new Map();   // key → { canvas, shader (a promise), sig, item, host, watch, dead }
  const ro = typeof ResizeObserver === 'function' && new ResizeObserver(es => { for (const e of es) for (const fx of kept.values()) if (fx.watch === e.target) place?.(fx); });
  const drop = (k, fx) => { if (ro && fx.watch) ro.unobserve(fx.watch); fx.shader.then(s => s?.destroy()); fx.canvas.remove(); kept.delete(k); };
  return (items, keep) => {
    const live = new Set();
    for (const it of items) {
      let fx = kept.get(it.key);
      if (fx && fx.sig !== it.sig) { drop(it.key, fx); fx = null; }
      if (!fx) {
        const ls = layers(it); if (!ls) continue;
        const canvas = fxCanvas(), f = { canvas, sig: it.sig, shader: mount(canvas, ls).catch(() => null) };
        if (it.cls) canvas.classList.add(it.cls);
        f.shader.then(s => { if (!s) { f.dead = true; canvas.remove(); } });   // failed to start: the CSS look, and no retries
        kept.set(it.key, fx = f);
      }
      live.add(it.key);
      if (fx.dead) continue;
      fx.item = it;
      const watch = it.watch || it.host;
      if (fx.watch !== watch) { if (ro) { if (fx.watch) ro.unobserve(fx.watch); ro.observe(watch); } fx.watch = watch; }
      if (fx.host !== it.host) { fx.host = it.host; it.host.prepend(fx.canvas); }
      place?.(fx);
      fx.shader.then(s => s?.resume());
    }
    for (const [k, fx] of kept) if (!live.has(k)) { if (keep) fx.shader.then(s => s?.pause()); else drop(k, fx); }
    return kept;
  };
}

/* ---------- weather ----------
   A card or table row carries data-wx (the sky, as the weather icons name it) and data-wind / data-rain / data-snow,
   each 0 (no effect) to about 1.5 (strong), the loads the model uses. "Weather games" (data-rough) move at full speed;
   the rest drift slower and fainter, so a page of fourteen games isn't busy. */
const dark = () => { const t = document.documentElement.dataset.theme; return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; };
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
function weatherLayers(ds) {
  const sky = ds.wx, wind = +ds.wind || 0, rain = +ds.rain || 0, snow = +ds.snow || 0, pace = ds.rough != null ? 1 : 0.5, d = dark();
  if (sky === 'rain' || sky === 'thunderstorm' || sky === 'sleet') {
    const c = d ? '#9cc3e6' : '#4d7ea8', heavy = clamp(rain, 0.3, 1.2) + (sky === 'thunderstorm' ? 0.3 : 0);
    return [{ type: 'FallingLines', props: { colorA: c, colorB: c + '00', angle: 90 - clamp(wind, 0, 1.5) * 22, speed: (1 + heavy * 0.8) * pace,
      speedVariance: 0.4, density: Math.round(14 + heavy * 22), trailLength: sky === 'sleet' ? 0.18 : 0.45, strokeWidth: 0.1, rounding: 1 } }];
  }
  if (sky === 'snow') {
    return [{ type: 'FloatingParticles', props: { count: Math.round(250 + clamp(snow, 0.3, 1.2) * 700), angle: 270 - clamp(wind, 0, 1.5) * 30,
      speed: (0.2 + clamp(wind, 0, 1.5) * 0.15) * pace, speedVariance: 0.4, angleVariance: 25, randomness: 0.35, twinkle: 0.15,
      particleSize: 2.3, softness: 0.4, shape: 'dot', particleColor: d ? '#e8f0f7' : '#7d98b3', cursorStrength: 0 } }];
  }
  if (wind >= 0.2) {
    const c = d ? '#7d9188' : '#97a69e';
    return [{ type: 'FallingLines', props: { colorA: c, colorB: c + '00', angle: 0, speed: (1.2 + wind) * pace, speedVariance: 0.5,
      density: Math.round(8 + wind * 8), trailLength: 0.6, strokeWidth: 0.035, rounding: 1 } }];
  }
  if (sky === 'fog') {
    return [{ type: 'Fog', props: { colorA: d ? '#2c3833' : '#dfe6e1', colorB: d ? '#1a231f' : '#c3cec6', speed: 0.5 * pace, turbulence: 0.6,
      detail: 10, blending: 0.6, mouseInfluence: 0 } }];
  }
  if (sky === 'sunny') {
    return [{ type: 'Godrays', props: { center: { x: 1, y: 0 }, rayColor: d ? '#e2bb52' : '#e0a526', backgroundColor: 'transparent',
      density: 0.22, intensity: 0.55, spotty: 0.4, speed: 0.25 * pace } }];
  }
  return null;   // cloudy, partly cloudy and clear nights stay plain
}
export function weatherCards(root = document) {
  for (const card of root.querySelectorAll('[data-wx]')) {
    const layers = weatherLayers(card.dataset); if (!layers) continue;
    const c = fxCanvas(); if (card.dataset.rough == null) c.classList.add('calm');
    card.prepend(c);
    mount(c, layers).catch(() => c.remove());
  }
}
/* The app's weather table: a row can't reliably hold a positioned box, so each canvas sits in the row's first cell and
   is sized to cover the whole row (re-fitted when the row resizes, as in the narrow-screen stacked layout). */
function overRow(fx) {
  const tr = fx.watch, td = fx.host, r = tr.getBoundingClientRect(), c = td.getBoundingClientRect(), st = fx.canvas.style;
  st.left = `${r.left - c.left - td.clientLeft}px`; st.top = `${r.top - c.top - td.clientTop}px`; st.width = `${r.width}px`; st.height = `${r.height}px`;
}
const syncRows = keeper(it => weatherLayers(it.ds), overRow);
export function weatherRows(rows, keep) {
  syncRows(rows.filter(tr => tr.cells.length).map(tr => { const ds = tr.dataset;
    return { key: ds.game, host: tr.cells[0], watch: tr, ds, cls: ds.rough == null ? 'calm' : '', sig: [ds.wx, ds.wind, ds.rain, ds.snow, ds.rough != null, dark()].join() }; }), keep);
}

/* ---------- welcome cards ----------
   Each "add your team" card gets a slow mesh gradient in its own --wl-bg (darker, the colour, lighter: the same three
   the CSS gradient under it uses) and a glass disc where the faint corner icon sits, bending the gradient as it moves.
   The canvases are kept across renders (keeper, above). */
const mix = (hex, to, t) => { const n = parseInt(hex.slice(1), 16), m = parseInt(to.slice(1), 16), ch = s => Math.round(((n >> s) & 255) * (1 - t) + ((m >> s) & 255) * t);
  return '#' + ((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0'); };
/* The lens sits on .wl-mark's icon, at its size, in the card's 0–1 coordinates; measured, since the icon moves on narrow
   screens. A circle of radius 0.42 at scale 1 is 0.42 of the card's shorter side across. */
function lens(b) {
  const r = b.getBoundingClientRect(), m = b.querySelector('.wl-mark svg')?.getBoundingClientRect();
  if (!m || !r.width || !r.height) return null;
  return { center: { x: (m.left + m.width / 2 - r.left) / r.width, y: (m.top + m.height / 2 - r.top) / r.height }, scale: m.width / 2 / (0.42 * Math.min(r.width, r.height)) };
}
function cardLayers(bg, at) {
  return [
    { type: 'MeshGradient', id: 'mesh', props: { stops: [{ color: mix(bg, '#000000', 0.4), position: 0 }, { color: bg, position: 0.4 }, { color: bg, position: 0.7 },
      { color: mix(bg, '#ffffff', 0.25), position: 1 }], colorSpace: 'oklab', count: 5, smoothness: 1.6, variation: 0.5, swirl: 0.2, drift: 0.45, speed: 0.25, seed: 3 } },
    { type: 'Glass', id: 'glass', props: { shape: { type: 'circleSDF', radius: 0.42 }, ...at,
      refraction: 0.7, thickness: 0.6, edgeSoftness: 0.15, blur: 0, aberration: 0.25, highlight: 0.18, fresnel: 0.25, lightAngle: 300 } },
  ];
}
// a card that changes size (the narrow-screen layout) moves its lens with the icon
const syncCards = keeper(it => { const at = lens(it.host); return at && cardLayers(it.bg, at); },
  fx => { const at = lens(fx.host); if (at) fx.shader.then(s => s?.update('glass', at)); });
export function platformCards(btns, keep) {
  const kept = syncCards(btns.map(b => ({ key: b.dataset.method, host: b, sig: '', bg: getComputedStyle(b).getPropertyValue('--wl-bg').trim() || '#075b37' })), keep);
  for (const b of btns) {
    const fx = kept.get(b.dataset.method); if (!fx || fx.dead) continue;
    // the lens bends harder on hover, as the corner icon turns
    b.onpointerenter = () => fx.shader.then(s => s?.update('glass', { refraction: 0.95, aberration: 0.4 }));
    b.onpointerleave = () => fx.shader.then(s => s?.update('glass', { refraction: 0.7, aberration: 0.25 }));
  }
}
