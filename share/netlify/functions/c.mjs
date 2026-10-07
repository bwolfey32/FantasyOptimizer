// A shared comment's link. Chat apps and social sites read this page's preview tags (the card from /ccard); people go
// straight on to the comment in his discussion on the site (talkJump in index.html). A comment that's gone still lands
// on his discussion when the link names him.
import { readComment, loadComment, commentHash } from '../../lib/comment.mjs';
import { who, linkPage, SITE } from '../../lib/card.mjs';
import { snippet } from '../../lib/sb.mjs';

export default async req => {
  const url = new URL(req.url), q = readComment(url.searchParams);
  if (!q) return linkPage({});
  const c = await loadComment(q.id).catch(e => { console.error(e); return null; });
  const pid = c?.player_id || q.p, p = pid ? await who(pid).catch(() => null) : null;
  if (!p) return linkPage({ cdnAge: 600 });
  const dest = `${SITE}/?utm_source=share&utm_medium=comment#${commentHash(pid, q.id)}`, cta = 'See the discussion on Benny’s Picks';
  if (!c) return linkPage({ title: `${p.name}: the discussion on Benny’s Picks`, desc: `What’s your take on ${p.name}? Join the discussion on Benny’s Picks.`, dest, cta, cdnAge: 600 });
  const by = c.handle || 'Someone';
  return linkPage({
    title: `${by} on ${p.name}`, desc: `“${snippet(c.body, 200)}” Join the ${p.name} discussion on Benny’s Picks.`,
    image: `${url.origin}/ccard?id=${q.id}`, alt: `${by}’s comment about ${p.name}`,
    self: `${url.origin}/c?${new URLSearchParams({ id: q.id, p: pid })}`, dest, cta, cdnAge: 3600,
  });
};
export const config = { path: '/c' };
