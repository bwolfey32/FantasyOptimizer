/* A shared league's power rankings, as carried by a share link (share.bennyspicks.us/l?id=&wk=&r=), drawn as a card
   for link previews. The link carries the league id and each team's grade (roster id and score, best first:
   r=3_88-1_84-…); the league and team names come from Sleeper's public API, never from the link, so a link can't
   put made-up names on the card. */
import { C, el, renderCard } from './card.mjs';

const SL = 'https://api.sleeper.app/v1';
// letter grades from scores, as Team Grade gives them (GRADE_CUTS in index.html)
const GRADE_CUTS = [[93, 'A+'], [87, 'A'], [83, 'A−'], [79, 'B+'], [75, 'B'], [71, 'B−'], [67, 'C+'], [63, 'C'], [59, 'C−'], [55, 'D+'], [50, 'D'], [0, 'F']];
export const letterOf = s => GRADE_CUTS.find(([c]) => s >= c)[1];
// each letter's colors, as the site's grade badges show them in the dark theme
const GRADE_C = { A: [C.good, '#1d4a35'], B: [C.good, '#18332a'], C: [C.muted, C.surface2], D: [C.warn, '#3a3020'], F: [C.bad, '#47231f'] };
export const MAX_TEAMS = 16;

/* The rankings in a share link, or null without a league id or two graded teams: { id, wk, r: [[rosterId, score]] },
   best first, at most MAX_TEAMS. */
export function readLeague(q) {
  const id = /^\d{6,24}$/.test(q.get('id') || '') ? q.get('id') : null; if (!id) return null;
  const n = parseFloat(q.get('wk')), wk = Number.isFinite(n) && n >= 1 && n <= 22 ? Math.round(n) : null, seen = new Set();
  const r = (q.get('r') || '').split('-').map(x => /^(\d{1,3})_(\d{1,3})$/.exec(x)).filter(Boolean).map(m => [+m[1], Math.min(100, +m[2])])
    .filter(([rid]) => rid >= 1 && !seen.has(rid) && seen.add(rid)).slice(0, MAX_TEAMS);
  return r.length >= 2 ? { id, wk, r } : null;
}
export const leagueQuery = L => new URLSearchParams({ id: L.id, ...(L.wk ? { wk: L.wk } : {}), r: L.r.map(([rid, s]) => `${rid}_${s}`).join('-') }).toString();

// the league from Sleeper: its name and each roster's team name (as the site names them, slTeams), kept for 10 minutes
const cache = new Map();
export async function leagueNames(id) {
  const c = cache.get(id); if (c && Date.now() - c.at < 6e5) return c.v;
  const get = async p => { const r = await fetch(`${SL}${p}`, { signal: AbortSignal.timeout(5000) }); if (!r.ok) throw new Error(`Sleeper ${p}: ${r.status}`); return r.json(); };
  const [lg, rosters, users] = await Promise.all([get(`/league/${id}`), get(`/league/${id}/rosters`), get(`/league/${id}/users`)]);
  if (!lg?.league_id || !Array.isArray(rosters)) return null;
  const byUser = Object.fromEntries((users || []).map(u => [u.user_id, u]));
  const teams = Object.fromEntries(rosters.map(r => { const u = byUser[r.owner_id]; return [r.roster_id, u?.metadata?.team_name || u?.display_name || `Team ${r.roster_id}`]; }));
  const v = { name: lg.name || 'Sleeper league', season: lg.season, teams };
  cache.set(id, { at: Date.now(), v });
  return v;
}
// the link's teams that the league has, with their names: [{ rank, name, score, letter }]
export function rankedTeams(L, names) {
  return L.r.filter(([rid]) => Object.hasOwn(names.teams, rid)).map(([rid, score], i) => ({ rank: i + 1, name: names.teams[rid], score, letter: letterOf(score) }));
}

/* The power rankings card: the league's name, then every team in two columns, rank, name, letter grade and score. Rows
   shrink to fit up to MAX_TEAMS. Returns PNG bytes, or null when the league or its teams aren't found. */
export async function renderLeagueCard(L) {
  const names = await leagueNames(L.id).catch(() => null); if (!names) return null;
  const teams = rankedTeams(L, names); if (teams.length < 2) return null;
  const per = Math.ceil(teams.length / 2), rowH = Math.min(54, Math.floor(320 / per)), fs = Math.round(rowH * 0.48);
  const row = t => { const [ink, bg] = GRADE_C[t.letter[0]];
    return el('div', { height: rowH, alignItems: 'center', borderBottom: `1px solid ${C.line}` },
      el('div', { width: fs * (teams.length >= 10 ? 2 : 1.6), fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: fs * 1.15, color: t.rank <= 3 ? C.gold : C.muted }, String(t.rank)),
      el('div', { flex: 1, minWidth: 0, fontSize: fs, color: C.ink, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', marginRight: 12 }, t.name),
      el('div', { width: fs * 2.1, height: rowH - 14, alignItems: 'center', justifyContent: 'center', borderRadius: 8, backgroundColor: bg, color: ink, fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: fs * 1.05, marginRight: 10 }, t.letter),
      el('div', { width: fs * 1.6, justifyContent: 'flex-end', fontFamily: 'Saira Condensed', fontWeight: 600, fontSize: fs * 1.05, color: C.ink }, String(t.score)));
  };
  const col = list => el('div', { flexDirection: 'column', flex: 1, minWidth: 0 }, list.map(row));
  const n = names.name.length, size = n <= 26 ? 50 : n <= 36 ? 42 : 34;
  return renderCard(`POWER RANKINGS${L.wk ? ` · WEEK ${L.wk}` : ''}`, [
    el('div', { fontFamily: 'Saira Condensed', fontWeight: 700, fontSize: size, lineHeight: 1.05, textTransform: 'uppercase', color: C.ink, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', marginTop: 8 }, names.name),
    el('div', { marginTop: 10 }, col(teams.slice(0, per)), el('div', { width: 44 }), col(teams.slice(per))),
    el('div', { fontSize: 20, color: C.muted, marginTop: 10 }, 'Benny Grade: each roster’s strength out of 100. Where does your team rank?')]);
}
