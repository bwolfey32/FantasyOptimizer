/* A shared start/sit call (Benny's Pick), as carried by a share link (share.bennyspicks.us/s?start=&sit=&wk=&e=&p=&f=&why=),
   drawn as a card for link previews. Players are looked up by Sleeper id in share-players.json, as for a waiver move;
   only the edge, the chance to outscore, the scoring and the one-line reason come from the link. */
import { C, el, who, dataUrl, idOf, numOf, renderCard } from './card.mjs';
import { side } from './move.mjs';

const SCORING = { ppr: 'PPR', half: 'Half-PPR', std: 'Standard' };
// the lean, as Benny's Pick names it (viewCompare in index.html)
export const leanOf = p => p == null ? '' : p < 55 ? 'Toss-up' : p < 65 ? 'Slight lean' : p < 80 ? 'Clear lean' : 'Strong lean';

/* The call in a share link, or null without two valid, different players. */
export function readCall(q) {
  const start = idOf(q, 'start'), sit = idOf(q, 'sit'); if (!start || !sit || start === sit) return null;
  const wk = numOf(q, 'wk', 1, 22), p = numOf(q, 'p', 50, 100);
  const why = (q.get('why') || '').replace(/−/g, '-').replace(/[“”]/g, '"').replace(/[^\p{L}\p{N} +\-–—·±×.,;:()%'’"/&]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 160).replace(/[.;,\s]+$/, '');
  return { start, sit, wk: wk && Math.round(wk), e: numOf(q, 'e', 0, 99), p: p && Math.round(p), f: SCORING[q.get('f')] ? q.get('f') : null, why };
}
// the call's query string, in a fixed order; `site` keeps only what the site reads (it works out the rest live)
export function callQuery(c, site) {
  const q = new URLSearchParams({ start: c.start, sit: c.sit });
  if (site) return q.toString();
  if (c.wk) q.set('wk', c.wk);
  if (c.e != null) q.set('e', c.e.toFixed(1));
  for (const k of ['p', 'f', 'why']) if (c[k] != null && c[k] !== '') q.set(k, c[k]);
  return q.toString();
}
export const scoringName = c => SCORING[c.f] || '';
export const callLine = c => [c.e != null ? `+${c.e.toFixed(1)} projected pts` : '', c.p ? `${c.p}% to outscore` : '', scoringName(c)].filter(Boolean).join(' · ');

/* The Benny's Pick card: who to start and who to sit, the projected edge, the lean and the first reason. Returns PNG
   bytes, or null if either player is unknown. */
export async function renderCallCard(c) {
  const [a, b] = await Promise.all([who(c.start), who(c.sit)]);
  if (!a || !b) return null;
  const [picA, picB] = await Promise.all([dataUrl(a.img), dataUrl(b.img)]);
  const lean = leanOf(c.p);
  return renderCard(`BENNY’S PICK${c.wk ? ` · WEEK ${c.wk}` : ''}`, [
    el('div', {},
      side('Start', C.good, a, picA, `${a.pos} · ${a.team}`),
      el('div', { width: 40 }),
      side('Sit', C.bad, b, picB, `${b.pos} · ${b.team}`)),
    el('div', { flexDirection: 'column' },
      el('div', { alignItems: 'flex-end' },
        c.e != null && el('div', { fontFamily: 'Saira Condensed', fontWeight: 600, fontSize: 112, lineHeight: 0.9, color: C.good, marginRight: 22 }, `+${c.e.toFixed(1)}`),
        el('div', { flexDirection: 'column', paddingBottom: 6 },
          lean && el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 34, letterSpacing: 1.2, color: C.gold }, lean.toUpperCase()),
          el('div', { fontSize: 28, color: C.muted }, [c.e != null ? 'projected pts edge' : '', c.p ? `${c.p}% to outscore` : '', scoringName(c)].filter(Boolean).join(' · ')))),
      c.why && el('div', { fontSize: 26, lineHeight: 1.4, marginTop: 18, maxHeight: 73, overflow: 'hidden' }, `${c.why}.`))]);
}
