/* Reads from the site's community database (Supabase) as an anonymous visitor, with the same public address and
   publishable key as CLOUD in index.html (change both together). It can read only what anyone can: hidden comments never
   come back, so a card can't show one. */
const SB = { url: 'https://hwfppigktdpjmnfretgo.supabase.co', key: 'sb_publishable_SsduRo6wMk1OZvEJH-2zMw_eHF8ygC4' };

// one REST read (`path` after /rest/v1/), as JSON; throws on an error or after 4 seconds
export async function sb(path) {
  const r = await fetch(`${SB.url}/rest/v1/${path}`, { headers: { apikey: SB.key }, signal: AbortSignal.timeout(4000) });
  if (!r.ok) throw new Error(`supabase ${path.split('?')[0]}: ${r.status}`);
  return r.json();
}
// a comment id, as the database makes them
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// a comment's text on one line, at most n characters (cut at a word, with an ellipsis)
export function snippet(s, n) {
  const t = String(s || '').replace(/\s+/g, ' ').trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n - 1), sp = cut.lastIndexOf(' ');
  return (sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s.,;:!?-]+$/, '') + '…';
}
