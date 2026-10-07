// A shared "Who would you start?" poll's link. Chat apps and social sites read this page's preview tags (the card from
// /vcard); people go straight on to Start / Sit on the site, with the same two players and the poll in view.
import { readPoll, pollQuery } from '../../lib/poll.mjs';
import { who, linkPage, SITE } from '../../lib/card.mjs';

export default async req => {
  const url = new URL(req.url), p = readPoll(url.searchParams);
  const dest = p ? `${SITE}/?utm_source=share&utm_medium=poll&${pollQuery(p, true)}#start-sit` : `${SITE}/`;
  const [a, b] = p ? await Promise.all([who(p.start), who(p.sit)]).catch(() => []) : [];
  if (!a || !b) return linkPage({ dest });
  return linkPage({
    title: `Who would you start: ${a.name} or ${b.name}?`,
    desc: `${p.wk ? `Week ${p.wk}. ` : ''}Cast your vote on Benny’s Picks and see what everyone else thinks.`,
    image: `${url.origin}/vcard?${pollQuery(p)}`, alt: `Who would you start: ${a.name} or ${b.name}?`,
    self: `${url.origin}/v?${pollQuery(p)}`, dest, cta: 'Vote, free',
  });
};
export const config = { path: '/v' };
