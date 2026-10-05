// The Best move card as a PNG, for a share link's preview (og:image on /w). An unknown player gets the site's own
// preview image instead.
import { readMove, renderCard, SITE } from '../../lib/move.mjs';

export default async req => {
  const m = readMove(new URL(req.url).searchParams);
  try {
    const png = m && await renderCard(m);
    if (png) return new Response(png, { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=31536000, immutable', 'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=31536000' } });
  } catch (e) { console.error(e); }
  return Response.redirect(`${SITE}/assets/social-preview.jpg`, 302);
};
export const config = { path: '/card' };
