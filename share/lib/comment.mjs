/* A shared comment (share.bennyspicks.us/c?id=&p=), drawn as a card for link previews. The link carries only the comment's
   id and his player id. The words, the username and the reactions are read from the community database, so a link can't
   put made-up words on a card. A hidden or deleted comment isn't drawn. */
import { C, el, who, dataUrl, idOf, renderCard } from './card.mjs';
import { sb, UUID } from './sb.mjs';
import { playerHead, quote } from './player.mjs';

/* The comment in a share link ({ id, p }), or null without a valid comment id. `p` (his player) is a fallback for when
   the comment can't be read. */
export function readComment(q) {
  const id = q.get('id'); if (!UUID.test(id || '')) return null;
  return { id: id.toLowerCase(), p: idOf(q, 'p') };
}
// where the link goes on the site: the comment, in his discussion (talkJump in index.html)
export const commentHash = (pid, cid) => `player/${encodeURIComponent(pid)}/talk/${cid}`;

/* The comment with its author's username, reaction counts (most used first) and visible replies; null if it's gone or hidden. */
export async function loadComment(cid) {
  const [rows, rx, kids] = await Promise.all([
    sb(`comments?id=eq.${cid}&deleted_at=is.null&select=id,player_id,body,week,profiles!comments_author_id_fkey(handle)`),
    sb(`reaction_counts?comment_id=eq.${cid}&select=emoji,n`),
    sb(`comments?parent_id=eq.${cid}&deleted_at=is.null&select=id&limit=200`)]);
  const c = rows[0]; if (!c?.body) return null;
  return { ...c, handle: c.profiles?.handle || null, rx: rx.filter(r => r.n > 0).sort((a, b) => b.n - a.n), replies: kids.length };
}

/* The comment's card: his picture and name, the words, then who wrote it, the reactions and the replies. Returns PNG
   bytes, or null if the player is unknown. */
export async function renderCommentCard(c) {
  const p = await who(c.player_id); if (!p) return null;
  const pic = await dataUrl(p.img);
  return renderCard(`DISCUSSION${c.week ? ` · WEEK ${c.week}` : ''}`, [
    playerHead(p, pic),
    quote(c.body, { chars: 230, lines: 4, sizes: [46, 38, 32] }),
    el('div', { alignItems: 'center', fontSize: 30, color: C.muted },
      el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: 38, color: C.good, marginRight: 28 }, c.handle ? `@${c.handle}` : 'Someone'),
      c.rx.slice(0, 4).map(r => el('div', { marginRight: 20 }, `${r.emoji} ${r.n}`)),
      c.replies > 0 && el('div', {}, `${c.replies} repl${c.replies === 1 ? 'y' : 'ies'}`))]);
}
