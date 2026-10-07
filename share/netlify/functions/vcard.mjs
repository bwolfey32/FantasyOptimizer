// The poll card as a PNG, for a shared poll's link preview (og:image on /v). An unknown player gets the site's own
// preview image instead.
import { readPoll, renderPollCard } from '../../lib/poll.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const p = readPoll(new URL(req.url).searchParams);
  try {
    const png = p && await renderPollCard(p);
    if (png) return pngResponse(png);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/vcard' };
