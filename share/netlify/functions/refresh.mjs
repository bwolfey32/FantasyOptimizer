// Starts the site's data refresh (.github/workflows/refresh-data.yml) every 3 hours. GitHub runs that workflow's own
// schedule late, or skips it, when GitHub is busy (about every 7 hours in October 2026), and the news on the player
// pages waited with it; this calls the workflow's on-demand trigger on time instead. GitHub's schedule stays on as a
// backup. A scheduled function has no address, so nobody else can start it.
// Needs GH_DISPATCH_TOKEN in Netlify's environment variables (see README.md).
const REPO = 'bwolfey32/FantasyOptimizer', WORKFLOW = 'refresh-data.yml';

export default async () => {
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) { console.error('GH_DISPATCH_TOKEN is not set, so the data refresh was not started'); return new Response('no token', { status: 500 }); }
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'bennys-picks-share' },
    body: JSON.stringify({ ref: 'main' }),
  });
  if (!r.ok) { console.error(`starting the data refresh failed: ${r.status} ${await r.text()}`); return new Response('failed', { status: 502 }); }
  console.log('data refresh started');
  return new Response('started');
};
export const config = { schedule: '17 */3 * * *' };
