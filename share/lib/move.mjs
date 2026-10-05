/* A shared waiver move, as carried by a share link (share.bennyspicks.us/w?add=&drop=&wk=&g=&h=&o=&why=):
   read and checked here, then drawn as the Best move card for link previews.
   Players are looked up by Sleeper id in share-players.json on the site (built daily by scripts/player_ids.py), so a
   link can't put a made-up name on the card. Only the numbers and the one-line reason come from the link. */
import { C, el, img, who, dataUrl, idOf, numOf, renderCard, SILHOUETTE } from './card.mjs';

/* The move in a share link, or null without a valid added player. Ids as the site checks them; numbers in range or
   null; the reason keeps letters, digits and plain punctuation, one line of at most 180 characters. */
export function readMove(q) {
  const add = idOf(q, 'add'); if (!add) return null;
  const wk = numOf(q, 'wk', 1, 22), h = numOf(q, 'h', 1, 18);
  const why = (q.get('why') || '').replace(/−/g, '-').replace(/[“”]/g, '"').replace(/[^\p{L}\p{N} +\-–—·±×.,;:()%'’"/&]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 180).replace(/[.;,\s]+$/, '');
  return { add, drop: idOf(q, 'drop'), wk: wk && Math.round(wk), g: numOf(q, 'g', 0, 999), h: h && Math.round(h), o: numOf(q, 'o', 0, 100), why };
}
// the move's query string, in a fixed order; `site` keeps only what the site reads (it shows its own reasons)
export function moveQuery(m, site) {
  const q = new URLSearchParams({ add: m.add });
  if (m.drop) q.set('drop', m.drop);
  for (const k of ['wk', 'g', 'h']) if (m[k] != null) q.set(k, k === 'g' ? m.g.toFixed(1) : m[k]);
  if (!site) { if (m.o != null) q.set('o', m.o); if (m.why) q.set('why', m.why); }
  return q.toString();
}
export const gainLine = m => m.g != null && m.h ? `expected lineup pts over the next ${m.h} week${m.h > 1 ? 's' : ''}` : '';
export const ownedText = o => o == null ? 'unowned' : o < 1 ? '<1% owned' : `${Math.round(o)}% owned`;

/* One player on a card: the label above (ADD, DROP, START, SIT…) in `color`, his picture, name and a line under it.
   With no player, `empty` in place of him. Shared with the Start / Sit card. */
export function side(label, color, p, pic, sub, empty) {
  const head = el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 30, letterSpacing: 2.4, color, marginBottom: 12 }, label.toUpperCase());
  if (!p) return el('div', { flexDirection: 'column', flex: 1, minWidth: 0 }, head, el('div', { fontSize: 28, color: C.muted, marginTop: 8 }, empty || ''));
  const n = p.name.length, size = n <= 13 ? 60 : n <= 17 ? 52 : 44;
  return el('div', { flexDirection: 'column', flex: 1, minWidth: 0 }, head,
    el('div', { alignItems: 'center' },
      el('div', { width: 136, height: 136, flexShrink: 0, borderRadius: 68, overflow: 'hidden', backgroundColor: C.surface2, alignItems: p.logo ? 'center' : 'flex-end', justifyContent: 'center', marginRight: 22 },
        pic ? img(pic, p.logo ? { width: 100, height: 100 } : { width: 187, height: 136, objectFit: 'cover' }) : img(SILHOUETTE, { width: 114, height: 114 })),
      el('div', { flexDirection: 'column', flex: 1, minWidth: 0 },
        el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: size, lineHeight: 1.02, textTransform: 'uppercase', color: C.ink }, p.name),
        el('div', { fontSize: 28, color: C.muted, marginTop: 6 }, sub))));
}

/* The Best move card: what to add and drop, the points it gains and why, under the Benny's Picks name. Returns PNG
   bytes, or null if the added player is unknown. */
export async function renderMoveCard(m) {
  const [a, d] = await Promise.all([who(m.add), who(m.drop)]);
  if (!a) return null;
  const [picA, picD] = await Promise.all([dataUrl(a.img), d ? dataUrl(d.img) : null]);
  const gain = gainLine(m);
  return renderCard(`BEST MOVE${m.wk ? ` · WEEK ${m.wk}` : ''}`, [
    el('div', {},
      side('Add', C.good, a, picA, `${a.pos} · ${a.team} · ${ownedText(m.o)}`),
      el('div', { width: 40 }),
      d ? side('Drop', C.bad, d, picD, `${d.pos} · ${d.team}`) : side('No drop', C.muted, null, null, '', 'Open roster spot')),
    el('div', { flexDirection: 'column' },
      gain && el('div', { alignItems: 'flex-end' },
        el('div', { fontFamily: 'Saira Condensed', fontWeight: 600, fontSize: 112, lineHeight: 0.9, color: C.good, marginRight: 22 }, `+${m.g.toFixed(1)}`),
        el('div', { fontSize: 30, color: C.muted, paddingBottom: 6 }, gain)),
      m.why && el('div', { fontSize: 26, lineHeight: 1.4, marginTop: gain ? 18 : 0, maxHeight: 73, overflow: 'hidden' }, `${m.why}.`))]);
}
