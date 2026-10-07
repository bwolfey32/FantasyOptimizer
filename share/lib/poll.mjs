/* A shared "Who would you start?" poll (share.bennyspicks.us/v?start=&sit=&wk=), drawn as a card for link previews. It
   asks the question and nothing more: no Benny's call and no crowd split, so whoever opens it votes first. Players are
   looked up by Sleeper id in share-players.json; only the week comes from the link. */
import { C, el, who, dataUrl, idOf, numOf, renderCard } from './card.mjs';
import { side } from './move.mjs';

/* The poll in a share link, or null without two valid, different players. */
export function readPoll(q) {
  const start = idOf(q, 'start'), sit = idOf(q, 'sit'); if (!start || !sit || start === sit) return null;
  const wk = numOf(q, 'wk', 1, 22);
  return { start, sit, wk: wk && Math.round(wk) };
}
// the poll's query string, in a fixed order; `site` keeps only what the site reads
export function pollQuery(p, site) {
  const q = new URLSearchParams({ start: p.start, sit: p.sit });
  if (site) q.set('poll', '1');
  else if (p.wk) q.set('wk', p.wk);
  return q.toString();
}

/* The poll card: the two players side by side in the same neutral color, with a versus between them. Returns PNG
   bytes, or null if either player is unknown. */
export async function renderPollCard(p) {
  const [a, b] = await Promise.all([who(p.start), who(p.sit)]);
  if (!a || !b) return null;
  const [picA, picB] = await Promise.all([dataUrl(a.img), dataUrl(b.img)]);
  return renderCard(`WHO WOULD YOU START?${p.wk ? ` · WEEK ${p.wk}` : ''}`, [
    el('div', { alignItems: 'center' },
      side('Player A', C.gold, a, picA, `${a.pos} · ${a.team}`),
      el('div', { width: 80, justifyContent: 'center', fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 40, color: C.muted }, 'VS'),
      side('Player B', C.gold, b, picB, `${b.pos} · ${b.team}`)),
    el('div', { fontSize: 30, color: C.muted }, 'Vote on Benny’s Picks to see what everyone else thinks.')]);
}
