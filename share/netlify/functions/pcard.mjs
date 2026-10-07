// A player's card as a PNG (og:image on /p, and on his static page). Kept a day (he can change teams), or an hour on the
// Discussion tab, which shows the newest comment. An unknown player gets the site's own preview image instead.
import { readPlayer, renderPlayerCard } from '../../lib/player.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const q = readPlayer(new URL(req.url).searchParams);
  try {
    const png = q && await renderPlayerCard(q);
    if (png) return pngResponse(png, q.t === 'talk' ? 3600 : 86400);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/pcard' };
