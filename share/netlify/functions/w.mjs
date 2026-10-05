// A shared waiver move's link. Chat apps and social sites read this page's preview tags (the card from /card);
// people go straight on to the site, which shows the move on Waivers (sharedMoveCard in index.html).
import { readMove, moveQuery, gainLine } from '../../lib/move.mjs';
import { who, linkPage, SITE } from '../../lib/card.mjs';

export default async req => {
  const url = new URL(req.url), m = readMove(url.searchParams);
  const [a, d] = m ? await Promise.all([who(m.add), who(m.drop)]).catch(() => []) : [];
  const dest = m ? `${SITE}/?utm_source=share&utm_medium=waiver_move&${moveQuery(m, true)}#waivers` : `${SITE}/`;
  if (!a) return linkPage({ dest });
  return linkPage({
    title: `Benny’s Picks: add ${a.name}${d ? `, drop ${d.name}` : ''}`,
    desc: [m.g != null && m.h ? `+${m.g.toFixed(1)} ${gainLine(m)}${m.wk ? ` (week ${m.wk})` : ''}.` : '', m.why ? `${m.why}.` : ''].filter(Boolean).join(' '),
    image: `${url.origin}/card?${moveQuery(m)}`, alt: `Best move: add ${a.name}${d ? `, drop ${d.name}` : ''}`,
    self: `${url.origin}/w?${moveQuery(m)}`, dest, cta: 'Find your best move, free',
  });
};
export const config = { path: '/w' };
