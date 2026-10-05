/* A shared waiver move, as carried by a share link (share.bennyspicks.us/w?add=&drop=&wk=&g=&h=&o=&why=):
   read and checked here, then drawn as the Best move card for link previews.
   Players are looked up by Sleeper id in share-players.json on the site (built daily by scripts/player_ids.py), so a
   link can't put a made-up name on the card. Only the numbers and the one-line reason come from the link. */
import satori from 'satori';
import { Resvg, initWasm } from '@resvg/resvg-wasm';

export const SITE = 'https://bennyspicks.us';
const RESVG_WASM = 'https://cdn.jsdelivr.net/npm/@resvg/resvg-wasm@2.6.2/index_bg.wasm';   // same version as package.json
const ESPN_IMG = 'https://a.espncdn.com/combiner/i?img=';
// team nicknames, for D/STs (TEAMS in index.html)
const TEAMS = { ARI: 'Cardinals', ATL: 'Falcons', BAL: 'Ravens', BUF: 'Bills', CAR: 'Panthers', CHI: 'Bears', CIN: 'Bengals', CLE: 'Browns', DAL: 'Cowboys', DEN: 'Broncos', DET: 'Lions', GB: 'Packers', HOU: 'Texans', IND: 'Colts', JAX: 'Jaguars', KC: 'Chiefs', LV: 'Raiders', LAC: 'Chargers', LAR: 'Rams', MIA: 'Dolphins', MIN: 'Vikings', NE: 'Patriots', NO: 'Saints', NYG: 'Giants', NYJ: 'Jets', PHI: 'Eagles', PIT: 'Steelers', SF: '49ers', SEA: 'Seahawks', TB: 'Buccaneers', TEN: 'Titans', WAS: 'Commanders' };
// the site's dark theme
const C = { bg: '#0e1512', surface: '#151e1a', surface2: '#1c2722', ink: '#e4ebe6', muted: '#a9b7af', line: '#29352f', good: '#4fc38e', bad: '#f07a6e', gold: '#e2bb52' };

/* The move in a share link, or null without a valid added player. Ids as the site checks them; numbers in range or
   null; the reason keeps letters, digits and plain punctuation, one line of at most 180 characters. */
export function readMove(q) {
  const id = k => /^[\w-]{1,12}$/.test(q.get(k) || '') ? q.get(k) : null;
  const num = (k, lo, hi) => { const n = parseFloat(q.get(k)); return Number.isFinite(n) && n >= lo && n <= hi ? n : null; };
  const add = id('add'); if (!add) return null;
  const wk = num('wk', 1, 22), h = num('h', 1, 18);
  const why = (q.get('why') || '').replace(/−/g, '-').replace(/[“”]/g, '"').replace(/[^\p{L}\p{N} +\-–—·±×.,;:()%'’"/&]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 180).replace(/[.;,\s]+$/, '');
  return { add, drop: id('drop'), wk: wk && Math.round(wk), g: num('g', 0, 999), h: h && Math.round(h), o: num('o', 0, 100), why };
}
// the move's query string, in a fixed order; `site` keeps only what the site reads (it shows its own reasons)
export function moveQuery(m, site) {
  const q = new URLSearchParams({ add: m.add });
  if (m.drop) q.set('drop', m.drop);
  for (const k of ['wk', 'g', 'h']) if (m[k] != null) q.set(k, k === 'g' ? m.g.toFixed(1) : m[k]);
  if (!site) { if (m.o != null) q.set('o', m.o); if (m.why) q.set('why', m.why); }
  return q.toString();
}

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
  if (TEAMS[id]) return { name: `${TEAMS[id]} D/ST`, pos: 'D/ST', team: id, img: `${ESPN_IMG}/i/teamlogos/nfl/500-dark/${id.toLowerCase()}.png&w=200&h=200`, logo: true };
  const x = (await players())[id]; if (!x) return null;
  const [name, pos, team, espn] = x;
  return { name, pos, team: team || 'FA', img: espn ? `${ESPN_IMG}/i/headshots/nfl/players/full/${espn}.png&w=330&h=240&scale=crop` : null };
}
export const gainLine = m => m.g != null && m.h ? `expected lineup pts over the next ${m.h} week${m.h > 1 ? 's' : ''}` : '';
export const ownedText = o => o == null ? 'unowned' : o < 1 ? '<1% owned' : `${Math.round(o)}% owned`;

/* ---------- drawing the card ---------- */
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
let wasm = null;
const resvgReady = () => wasm || (wasm = initWasm(fetch(RESVG_WASM)).catch(e => { wasm = null; throw e; }));
// an image as a data URL, or null if it doesn't load in time (the card then shows a silhouette)
async function dataUrl(src) {
  if (!src) return null;
  try {
    const r = await fetch(src, { signal: AbortSignal.timeout(4000) });
    if (!r.ok) return null;
    return `data:${r.headers.get('content-type') || 'image/png'};base64,${Buffer.from(await r.arrayBuffer()).toString('base64')}`;
  } catch { return null; }
}
const SILHOUETTE = `data:image/svg+xml;base64,${Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="15" r="7.5" fill="#4b5a52"/><path d="M5 40c0-9 6.7-14.5 15-14.5S35 31 35 40z" fill="#4b5a52"/></svg>`).toString('base64')}`;

// satori takes plain { type, props } objects; every box with several children is a flex box
const el = (type, style, ...children) => ({ type, props: { style: { display: 'flex', ...style }, children: children.flat().filter(c => c !== '' && c != null && c !== false) } });
const img = (src, style) => ({ type: 'img', props: { src, style } });

function side(kind, p, pic, sub) {
  const color = kind === 'Add' ? C.good : kind === 'Drop' ? C.bad : C.muted;
  const label = el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 30, letterSpacing: 2.4, color, marginBottom: 12 }, kind.toUpperCase());
  if (!p) return el('div', { flexDirection: 'column', flex: 1, minWidth: 0 }, label, el('div', { fontSize: 28, color: C.muted, marginTop: 8 }, 'Open roster spot'));
  const n = p.name.length, size = n <= 13 ? 60 : n <= 17 ? 52 : 44;
  return el('div', { flexDirection: 'column', flex: 1, minWidth: 0 }, label,
    el('div', { alignItems: 'center' },
      el('div', { width: 136, height: 136, flexShrink: 0, borderRadius: 68, overflow: 'hidden', backgroundColor: C.surface2, alignItems: p.logo ? 'center' : 'flex-end', justifyContent: 'center', marginRight: 22 },
        pic ? img(pic, p.logo ? { width: 100, height: 100 } : { width: 187, height: 136, objectFit: 'cover' }) : img(SILHOUETTE, { width: 114, height: 114 })),
      el('div', { flexDirection: 'column', flex: 1, minWidth: 0 },
        el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: size, lineHeight: 1.02, textTransform: 'uppercase', color: C.ink }, p.name),
        el('div', { fontSize: 28, color: C.muted, marginTop: 6 }, sub))));
}

/* The Best move card at 1200×630 (the size link previews use), in the site's dark theme: what to add and drop, the
   points it gains and why, under the Benny's Picks name. Returns PNG bytes, or null if the added player is unknown. */
export async function renderCard(m) {
  const [a, d] = await Promise.all([who(m.add), who(m.drop)]);
  if (!a) return null;
  const [fonts, picA, picD, icon] = await Promise.all([
    Promise.all([font('Saira Condensed', 600), font('Saira Condensed', 700), font('IBM Plex Sans', 400)]),
    dataUrl(a.img), d ? dataUrl(d.img) : null, dataUrl(`${SITE}/assets/icon-192.png`), resvgReady()]);
  const gain = gainLine(m);
  const card = el('div', { width: 1200, height: 630, padding: 28, backgroundColor: C.bg, fontFamily: 'IBM Plex Sans', color: C.ink },
    el('div', { flex: 1, flexDirection: 'column', justifyContent: 'space-between', padding: '40px 52px 44px', backgroundColor: C.surface, border: `3px solid ${C.good}`, borderRadius: 24 },
      el('div', { justifyContent: 'space-between', alignItems: 'center' },
        el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 30, letterSpacing: 2.4, color: C.gold }, `BEST MOVE${m.wk ? ` · WEEK ${m.wk}` : ''}`),
        el('div', { alignItems: 'center' },
          icon && img(icon, { width: 48, height: 48, borderRadius: 10, marginRight: 14 }),
          el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 32, letterSpacing: 1, color: C.ink }, 'BENNY’S PICKS'))),
      el('div', {},
        side('Add', a, picA, `${a.pos} · ${a.team} · ${ownedText(m.o)}`),
        el('div', { width: 40 }),
        side(d ? 'Drop' : 'No drop', d, picD, d ? `${d.pos} · ${d.team}` : '')),
      el('div', { flexDirection: 'column' },
        gain && el('div', { alignItems: 'flex-end' },
          el('div', { fontFamily: 'Saira Condensed', fontWeight: 600, fontSize: 112, lineHeight: 0.9, color: C.good, marginRight: 22 }, `+${m.g.toFixed(1)}`),
          el('div', { fontSize: 30, color: C.muted, paddingBottom: 6 }, gain)),
        m.why && el('div', { fontSize: 26, lineHeight: 1.4, marginTop: gain ? 18 : 0, maxHeight: 73, overflow: 'hidden' }, `${m.why}.`))));
  const svg = await satori(card, { width: 1200, height: 630, fonts });
  return new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng();
}
