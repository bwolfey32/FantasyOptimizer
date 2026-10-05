// A shared league's power rankings link. Chat apps and social sites read this page's preview tags (the card from
// /lcard); people go straight on to the site, which ranks the league live and lets them pick their own team
// (sharedLeagueCard in index.html).
import { readLeague, leagueQuery, leagueNames, rankedTeams } from '../../lib/league.mjs';
import { linkPage, SITE } from '../../lib/card.mjs';

export default async req => {
  const url = new URL(req.url), L = readLeague(url.searchParams);
  const dest = L ? `${SITE}/?utm_source=share&utm_medium=power_rankings&league=${L.id}#lineup` : `${SITE}/`;
  const names = L ? await leagueNames(L.id).catch(() => null) : null, teams = names ? rankedTeams(L, names) : [];
  if (teams.length < 2) return linkPage({ dest });
  return linkPage({
    title: `Benny’s power rankings: ${names.name}${L.wk ? `, week ${L.wk}` : ''}`,
    desc: `${teams.slice(0, 3).map(t => `${t.rank}. ${t.name} (${t.letter})`).join(', ')}. Every roster graded out of 100. Where does yours rank?`,
    image: `${url.origin}/lcard?${leagueQuery(L)}`, alt: `Power rankings for ${names.name}`,
    self: `${url.origin}/l?${leagueQuery(L)}`, dest, cta: 'See where your team ranks, free',
  });
};
export const config = { path: '/l' };
