/* A shared player page (share.bennyspicks.us/p?id=&t=), drawn as a card for link previews. He is looked up by Sleeper
   id in share-players.json, so a link can't put a made-up name on the card. The link says only which tab of his page was
   shared. For his Discussion tab, the comment count and the newest comment are read from the community database. The
   static player pages (scripts/player_pages.py) use his overview card as their preview picture. */
import { C, el, img, who, dataUrl, idOf, renderCard, SILHOUETTE } from './card.mjs';
import { sb, snippet } from './sb.mjs';

// the tabs of his page (PTABS in index.html): the card's kicker, and the line under his name
const TABS = {
  overview: ['PLAYER', 'Weekly projection, game log, news and discussion'],
  news: ['NEWS', 'The latest news, injury updates and depth-chart moves'],
  talk: ['DISCUSSION', ''],
  games: ['GAME LOG', 'Every game this season, in fantasy points'],
  history: ['HISTORY', 'His fantasy finishes, season by season'],
  stats: ['STATS', 'His season stats and usage'],
};
/* The player in a share link ({ id, t }), or null without a valid id. An unknown tab is his overview. */
export function readPlayer(q) {
  const id = idOf(q, 'id'); if (!id) return null;
  const t = q.get('t'); return { id, t: Object.hasOwn(TABS, t) ? t : 'overview' };
}
export const playerQuery = q => new URLSearchParams(q.t === 'overview' ? { id: q.id } : { id: q.id, t: q.t }).toString();
// his page's address on the site (playerHash in index.html)
export const playerHash = q => `player/${encodeURIComponent(q.id)}${q.t === 'overview' ? '' : '/' + q.t}`;
export const posTeam = p => p.logo ? 'Defense / special teams' : `${p.pos} · ${p.team === 'FA' ? 'Free agent' : p.team}`;

/* His discussion: { n: comments (not hidden or deleted), top: the newest first comment { body, handle } or null }, or
   null when the database can't be reached. */
export async function talkOf(id) {
  try {
    const pid = encodeURIComponent(id);
    const [cnt, rows] = await Promise.all([
      sb(`discussion_counts?select=n&player_id=eq.${pid}`),
      sb(`comments?select=body,profiles!comments_author_id_fkey(handle)&player_id=eq.${pid}&parent_id=is.null&deleted_at=is.null&order=created_at.desc&limit=1`)]);
    return { n: cnt[0]?.n || 0, top: rows[0]?.body ? { body: rows[0].body, handle: rows[0].profiles?.handle || null } : null };
  } catch (e) { console.error(e); return null; }
}

/* Him across a card: picture, name, and position · team. `big` on his own card; smaller above a comment. */
export function playerHead(p, pic, big) {
  const d = big ? 172 : 112, n = p.name.length, size = big ? (n <= 16 ? 84 : n <= 22 ? 68 : 56) : (n <= 18 ? 56 : 46);
  return el('div', { alignItems: 'center' },
    el('div', { width: d, height: d, flexShrink: 0, borderRadius: d / 2, overflow: 'hidden', backgroundColor: C.surface2, alignItems: p.logo ? 'center' : 'flex-end', justifyContent: 'center', marginRight: 28 },
      pic ? img(pic, p.logo ? { width: Math.round(d * 0.74), height: Math.round(d * 0.74) } : { width: Math.round(d * 1.375), height: d, objectFit: 'cover' })
        : img(SILHOUETTE, { width: Math.round(d * 0.84), height: Math.round(d * 0.84) })),
    el('div', { flexDirection: 'column', flex: 1, minWidth: 0 },
      el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: size, lineHeight: 1.02, textTransform: 'uppercase', color: C.ink }, p.name),
      el('div', { fontSize: big ? 32 : 28, color: C.muted, marginTop: 6 }, posTeam(p))));
}
// someone's words in quotes, cut to `chars` and sized so they fit `lines` lines
export function quote(body, { chars, lines, sizes }) {
  const s = snippet(body, chars), size = s.length <= chars * 0.4 ? sizes[0] : s.length <= chars * 0.7 ? sizes[1] : sizes[2];
  return el('div', { fontSize: size, lineHeight: 1.35, maxHeight: Math.round(size * 1.35 * lines), overflow: 'hidden', color: C.ink }, `“${s}”`);
}

/* His card: his picture, name and team, under a kicker naming the tab that was shared. On the Discussion tab it gives
   the comment count and the newest comment. Returns PNG bytes, or null if he's unknown. */
export async function renderPlayerCard(q) {
  const p = await who(q.id); if (!p) return null;
  const [pic, talk] = await Promise.all([dataUrl(p.img), q.t === 'talk' ? talkOf(q.id) : null]);
  const [kicker, line] = TABS[q.t];
  let foot;
  if (q.t !== 'talk') foot = el('div', { fontSize: 34, color: C.muted }, line);
  else if (!talk?.top) foot = el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 44, color: C.good }, `What’s your take on ${p.name}?`);
  else foot = el('div', { flexDirection: 'column' },
    // the username as its owner typed it, so not in capitals like the kicker
    el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 38, letterSpacing: 0.5, color: C.good, marginBottom: 10 }, `${talk.n} comment${talk.n === 1 ? '' : 's'}${talk.top.handle ? ` · newest from @${talk.top.handle}` : ''}`),
    quote(talk.top.body, { chars: 150, lines: 2, sizes: [34, 32, 30] }));
  return renderCard(kicker, [playerHead(p, pic, true), foot]);
}
