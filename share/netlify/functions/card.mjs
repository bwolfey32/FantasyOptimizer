// The Best move card as a PNG, for a share link's preview (og:image on /w). An unknown player gets the site's own
// preview image instead.
import { readMove, renderMoveCard } from '../../lib/move.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const m = readMove(new URL(req.url).searchParams);
  try {
    const png = m && await renderMoveCard(m);
    if (png) return pngResponse(png);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/card' };
