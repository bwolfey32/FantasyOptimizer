// Opens Stripe's Customer Portal for the signed-in person (cancel the monthly plan, change card, see receipts).
// Returns { url }. Secrets: STRIPE_SECRET_KEY, SITE_URL.
import Stripe from 'npm:stripe@18.0.0';
import { createClient } from 'npm:@supabase/supabase-js@2';

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY')!, { apiVersion: '2025-03-31.basil', httpClient: Stripe.createFetchHttpClient() });
// browsers may call this only from the site itself (or a local copy for testing); the sign-in token is still required
const ORIGINS = ['https://bennyspicks.us', 'http://localhost:8000'];
const corsFor = (req: Request) => {
  const o = req.headers.get('Origin') || '';
  return { 'Access-Control-Allow-Origin': ORIGINS.includes(o) ? o : ORIGINS[0], 'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type', 'Access-Control-Allow-Methods': 'POST, OPTIONS', Vary: 'Origin' };
};

Deno.serve(async (req) => {
  const cors = corsFor(req);
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  try {
    const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
    const token = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
    const { data: { user } } = await admin.auth.getUser(token);
    if (!user) return json({ error: 'Sign in first.' }, 401);
    const { data: ent } = await admin.from('entitlements').select('stripe_customer_id').eq('user_id', user.id).maybeSingle();
    if (!ent?.stripe_customer_id) return json({ error: 'No purchases on this account yet.' }, 404);
    const site = Deno.env.get('SITE_URL') || 'https://bennyspicks.us/';
    const session = await stripe.billingPortal.sessions.create({ customer: ent.stripe_customer_id, return_url: new URL('#pro', site).toString() });
    return json({ url: session.url });
  } catch (e) {
    console.error(e);
    return json({ error: 'Couldn’t open billing. Try again in a moment.' }, 500);
  }
});
