// A shared player page's link. Chat apps and social sites read this page's preview tags (the card from /pcard); people
// go straight on to the same tab of his page on the site.
import { readPlayer, playerQuery, playerHash, posTeam, talkOf } from '../../lib/player.mjs';
import { who, linkPage, SITE } from '../../lib/card.mjs';
import { snippet } from '../../lib/sb.mjs';

export default async req => {
  const url = new URL(req.url), q = readPlayer(url.searchParams);
  const p = q ? await who(q.id).catch(() => null) : null;
  if (!p) return linkPage({});
  const dest = `${SITE}/?utm_source=share&utm_medium=player#${playerHash(q)}`, talk = q.t === 'talk';
  const d = talk ? await talkOf(q.id) : null;
  return linkPage({
    title: talk ? `${p.name}: the discussion on Benny’s Picks` : `${p.name} on Benny’s Picks`,
    desc: d?.top ? `${d.n} comment${d.n === 1 ? '' : 's'}. Newest${d.top.handle ? `, from ${d.top.handle}` : ''}: “${snippet(d.top.body, 140)}”`
      : talk ? `What’s your take on ${p.name}? Join the discussion on Benny’s Picks.`
      : `${p.name} (${posTeam(p)}): this week’s projection, game log, news and discussion. Free.`,
    image: `${url.origin}/pcard?${playerQuery(q)}`, alt: `${p.name} on Benny’s Picks`,
    self: `${url.origin}/p?${playerQuery(q)}`, dest, cta: talk ? 'Join the discussion on Benny’s Picks' : `See ${p.name} on Benny’s Picks`,
    cdnAge: talk ? 3600 : 86400,
  });
};
export const config = { path: '/p' };
