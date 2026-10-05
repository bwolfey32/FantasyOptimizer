// A shared start/sit call's link. Chat apps and social sites read this page's preview tags (the card from /scard);
// people go straight on to Start / Sit on the site, with the same two players (viewCompare in index.html).
import { readCall, callQuery, callLine, leanOf } from '../../lib/call.mjs';
import { who, linkPage, SITE } from '../../lib/card.mjs';

export default async req => {
  const url = new URL(req.url), c = readCall(url.searchParams);
  const dest = c ? `${SITE}/?utm_source=share&utm_medium=start_sit&${callQuery(c, true)}#start-sit` : `${SITE}/`;
  const [a, b] = c ? await Promise.all([who(c.start), who(c.sit)]).catch(() => []) : [];
  if (!a || !b) return linkPage({ dest });
  const lean = leanOf(c.p), line = callLine(c);
  return linkPage({
    title: `Benny’s Pick: start ${a.name} over ${b.name}`,
    desc: [`${lean ? lean + (line ? ': ' : '') : ''}${line}${c.wk ? ` (week ${c.wk})` : ''}.`, c.why ? `${c.why}.` : ''].filter(s => s && s !== '.').join(' '),
    image: `${url.origin}/scard?${callQuery(c)}`, alt: `Benny’s Pick: start ${a.name} over ${b.name}`,
    self: `${url.origin}/s?${callQuery(c)}`, dest, cta: 'Get Benny’s Pick for any two players, free',
  });
};
export const config = { path: '/s' };
