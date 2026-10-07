/* What every share card and link page has in common: the site's players (who), fonts, the resvg engine, satori's
   element helpers, and the preview page each link serves (linkPage). Cards are 1200×630, the size link previews use,
   in the site's dark theme. */
import satori from 'satori';
import { Resvg, initWasm } from '@resvg/resvg-wasm';

export const SITE = 'https://bennyspicks.us';
const RESVG_WASM = 'https://cdn.jsdelivr.net/npm/@resvg/resvg-wasm@2.6.2/index_bg.wasm';   // same version as package.json
const ESPN_IMG = 'https://a.espncdn.com/combiner/i?img=';
// team nicknames, for D/STs (TEAMS in index.html)
export const TEAMS = { ARI: 'Cardinals', ATL: 'Falcons', BAL: 'Ravens', BUF: 'Bills', CAR: 'Panthers', CHI: 'Bears', CIN: 'Bengals', CLE: 'Browns', DAL: 'Cowboys', DEN: 'Broncos', DET: 'Lions', GB: 'Packers', HOU: 'Texans', IND: 'Colts', JAX: 'Jaguars', KC: 'Chiefs', LV: 'Raiders', LAC: 'Chargers', LAR: 'Rams', MIA: 'Dolphins', MIN: 'Vikings', NE: 'Patriots', NO: 'Saints', NYG: 'Giants', NYJ: 'Jets', PHI: 'Eagles', PIT: 'Steelers', SF: '49ers', SEA: 'Seahawks', TB: 'Buccaneers', TEN: 'Titans', WAS: 'Commanders' };
// the site's dark theme
export const C = { bg: '#0e1512', surface: '#151e1a', surface2: '#1c2722', ink: '#e4ebe6', muted: '#a9b7af', line: '#29352f', good: '#4fc38e', bad: '#f07a6e', gold: '#e2bb52', warn: '#e3b052' };

// the site's player list, kept for an hour between requests
let roster = null;
async function players() {
  if (roster && Date.now() - roster.at < 36e5) return roster.p;
  const r = await fetch(`${SITE}/share-players.json`);
  if (!r.ok) throw new Error(`share-players.json: ${r.status}`);
  roster = { at: Date.now(), p: (await r.json()).p };
  return roster.p;
}
/* { name, pos, team, img } for a Sleeper id (a team abbreviation is its D/ST), or null if the site doesn't know him. */
export async function who(id) {
  if (!id) return null;
  // own keys only: an id like "constructor" is no team and no player
  if (Object.hasOwn(TEAMS, id)) return { name: `${TEAMS[id]} D/ST`, pos: 'D/ST', team: id, img: `${ESPN_IMG}/i/teamlogos/nfl/500-dark/${id.toLowerCase()}.png&w=200&h=200`, logo: true };
  const p = await players(), x = Object.hasOwn(p, id) ? p[id] : null; if (!Array.isArray(x)) return null;
  const [name, pos, team, espn] = x;
  return { name, pos, team: team || 'FA', img: espn ? `${ESPN_IMG}/i/headshots/nfl/players/full/${espn}.png&w=330&h=240&scale=crop` : null };
}
// a link's id, as the site checks them
export const idOf = (q, k) => /^[\w-]{1,12}$/.test(q.get(k) || '') ? q.get(k) : null;
// a number from a link, in range, or null
export const numOf = (q, k, lo, hi) => { const n = parseFloat(q.get(k)); return Number.isFinite(n) && n >= lo && n <= hi ? n : null; };

/* ---------- drawing ---------- */
// fonts, from Google Fonts as TrueType (what satori reads), kept between requests
const fontCache = new Map();
async function font(family, weight) {
  const k = `${family}:${weight}`;
  if (!fontCache.has(k)) fontCache.set(k, (async () => {
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family.replace(/ /g, '+')}:wght@${weight}`)).text();
    const src = css.match(/src: url\((.+?)\) format\('(opentype|truetype)'\)/)?.[1];
    if (!src) throw new Error(`no TrueType file for ${k}`);
    return { name: family, weight, style: 'normal', data: await (await fetch(src)).arrayBuffer() };
  })().catch(e => { fontCache.delete(k); throw e; }));
  return fontCache.get(k);
}
/* Emoji (in comments and reaction counts) as Twemoji pictures, since the fonts have none. Other scripts the fonts lack
   are left out. */
const TWEMOJI = 'https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/';
const emojiCache = new Map();
async function extraAsset(code, seg) {
  if (code !== 'emoji') return [];
  // Twemoji's file names: the code points in hex, without the variation selector unless it's a joined sequence
  const cps = [...seg].map(c => c.codePointAt(0)), name = (cps.includes(0x200d) ? cps : cps.filter(c => c !== 0xfe0f)).map(c => c.toString(16)).join('-');
  if (!emojiCache.has(name)) emojiCache.set(name, dataUrl(TWEMOJI + name + '.svg'));
  return (await emojiCache.get(name)) || '';
}
let wasm = null;
const resvgReady = () => wasm || (wasm = initWasm(fetch(RESVG_WASM)).catch(e => { wasm = null; throw e; }));
// an image as a data URL, or null if it doesn't load in time (the card then shows a silhouette)
export async function dataUrl(src) {
  if (!src) return null;
  try {
    const r = await fetch(src, { signal: AbortSignal.timeout(4000) });
    if (!r.ok) return null;
    return `data:${r.headers.get('content-type') || 'image/png'};base64,${Buffer.from(await r.arrayBuffer()).toString('base64')}`;
  } catch { return null; }
}
export const SILHOUETTE = `data:image/svg+xml;base64,${Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="15" r="7.5" fill="#4b5a52"/><path d="M5 40c0-9 6.7-14.5 15-14.5S35 31 35 40z" fill="#4b5a52"/></svg>`).toString('base64')}`;

// satori takes plain { type, props } objects; every box with several children is a flex box
export const el = (type, style, ...children) => ({ type, props: { style: { display: 'flex', ...style }, children: children.flat().filter(c => c !== '' && c != null && c !== false) } });
export const img = (src, style) => ({ type: 'img', props: { src, style } });

/* A card: the green-edged panel, with the gold kicker line (e.g. "BEST MOVE · WEEK 5") and the Benny's Picks name across
   the top, and `body` (the card's own boxes) below. Returns PNG bytes. */
export async function renderCard(kicker, body) {
  const [fonts, icon] = await Promise.all([
    Promise.all([font('Saira Condensed', 600), font('Saira Condensed', 700), font('IBM Plex Sans', 400)]),
    dataUrl(`${SITE}/assets/icon-192.png`), resvgReady()]);
  const card = el('div', { width: 1200, height: 630, padding: 28, backgroundColor: C.bg, fontFamily: 'IBM Plex Sans', color: C.ink },
    el('div', { flex: 1, flexDirection: 'column', justifyContent: 'space-between', padding: '40px 52px 44px', backgroundColor: C.surface, border: `3px solid ${C.good}`, borderRadius: 24 },
      el('div', { justifyContent: 'space-between', alignItems: 'center' },
        el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 30, letterSpacing: 2.4, color: C.gold }, kicker),
        el('div', { alignItems: 'center' },
          icon && img(icon, { width: 48, height: 48, borderRadius: 10, marginRight: 14 }),
          el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 32, letterSpacing: 1, color: C.ink }, 'BENNY’S PICKS'))),
      ...[body].flat()));
  const svg = await satori(card, { width: 1200, height: 630, fonts, loadAdditionalAsset: extraAsset });
  return new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng();
}
/* A card as the function's response, cached for good (a move's or a call's link never changes), or for `cdnAge`
   seconds when what it shows can change (a comment can be hidden or deleted); fallbackImage when there's nothing to draw */
export function pngResponse(png, cdnAge) {
  return new Response(png, { headers: { 'Content-Type': 'image/png',
    'Cache-Control': cdnAge ? 'public, max-age=300' : 'public, max-age=31536000, immutable',
    'Netlify-CDN-Cache-Control': `public, durable, s-maxage=${cdnAge || 31536000}` } });
}
export const fallbackImage = () => Response.redirect(`${SITE}/assets/social-preview.jpg`, 302);

/* ---------- the link's page ---------- */
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const DEFAULT_TITLE = 'Benny’s Picks — Fantasy Optimizer';
export const DEFAULT_DESC = 'Free weekly lineup optimizer for Sleeper and ESPN fantasy football: start/sit calls, waiver pickups, league power rankings and matchup breakdowns, with live data.';
/* The page a share link serves: preview tags for chat apps and social sites (title, description, the card), and a
   redirect that sends people straight on to `dest` on the site. Kept at the CDN for a day, or `cdnAge` seconds. */
export function linkPage({ title = DEFAULT_TITLE, desc = DEFAULT_DESC, image = `${SITE}/assets/social-preview.jpg`, alt = 'Benny’s Picks logo', self = `${SITE}/`, dest = `${SITE}/`, cta = 'Open Benny’s Picks, free', cdnAge = 86400 }) {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Benny’s Picks">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${esc(self)}">
<meta property="og:image" content="${esc(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#075b37">
<script>location.replace(${JSON.stringify(dest).replace(/</g, '\\u003c')})</script>
</head><body style="background:#0e1512;color:#e4ebe6;font:16px system-ui,sans-serif;padding:24px">
<p><a href="${esc(dest)}" style="color:#4fc38e;font-weight:600">${esc(cta)}</a></p>
</body></html>`;
  return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=300', 'Netlify-CDN-Cache-Control': `public, durable, s-maxage=${cdnAge}` } });
}
