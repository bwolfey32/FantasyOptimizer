// A shared waiver move's link. Chat apps and social sites read this page's preview tags (the card from /card);
// people go straight on to the site, which shows the move on Waivers (sharedMoveCard in index.html).
import { readMove, moveQuery, who, gainLine, SITE } from '../../lib/move.mjs';

const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export default async req => {
  const url = new URL(req.url), m = readMove(url.searchParams);
  const [a, d] = m ? await Promise.all([who(m.add), who(m.drop)]).catch(() => []) : [];
  const dest = m ? `${SITE}/?utm_source=share&utm_medium=waiver_move&${moveQuery(m, true)}#waivers` : `${SITE}/`;
  let title = 'Benny’s Picks — Fantasy Optimizer', desc = 'Free weekly lineup optimizer for ESPN fantasy football: start/sit calls, matchup and scheme breakdowns, and waiver pickups, with live data.';
  let image = `${SITE}/assets/social-preview.jpg`, alt = 'Benny’s Picks logo', self = `${SITE}/`;
  if (a) {
    title = `Benny’s Picks: add ${a.name}${d ? `, drop ${d.name}` : ''}`;
    desc = [m.g != null && m.h ? `+${m.g.toFixed(1)} ${gainLine(m)}${m.wk ? ` (week ${m.wk})` : ''}.` : '', m.why ? `${m.why}.` : ''].filter(Boolean).join(' ');
    image = `${url.origin}/card?${moveQuery(m)}`; alt = `Best move: add ${a.name}${d ? `, drop ${d.name}` : ''}`;
    self = `${url.origin}/w?${moveQuery(m)}`;
  }
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Benny’s Picks">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${esc(self)}">
<meta property="og:image" content="${esc(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#075b37">
<script>location.replace(${JSON.stringify(dest).replace(/</g, '\u003c')})</script>
</head><body style="background:#0e1512;color:#e4ebe6;font:16px system-ui,sans-serif;padding:24px">
<p><a href="${esc(dest)}" style="color:#4fc38e;font-weight:600">Find your best move, free</a></p>
</body></html>`;
  return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=300', 'Netlify-CDN-Cache-Control': 'public, durable, s-maxage=86400' } });
};
export const config = { path: '/w' };
