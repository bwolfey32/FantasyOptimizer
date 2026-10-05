// The Benny's Pick card as a PNG, for a shared start/sit call's link preview (og:image on /s). An unknown player gets
// the site's own preview image instead.
import { readCall, renderCallCard } from '../../lib/call.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const c = readCall(new URL(req.url).searchParams);
  try {
    const png = c && await renderCallCard(c);
    if (png) return pngResponse(png);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/scard' };
