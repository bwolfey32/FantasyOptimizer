// The power rankings card as a PNG, for a shared league's link preview (og:image on /l). A league Sleeper doesn't have
// gets the site's own preview image instead.
import { readLeague, renderLeagueCard } from '../../lib/league.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const L = readLeague(new URL(req.url).searchParams);
  try {
    const png = L && await renderLeagueCard(L);
    if (png) return pngResponse(png);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/lcard' };
