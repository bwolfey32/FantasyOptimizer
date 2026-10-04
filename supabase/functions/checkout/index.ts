// Starts a Stripe Checkout for Benny's Picks Pro. Called by the site with the signed-in person's token and
// { plan: 'monthly' | 'season' }; returns { url } for the Stripe-hosted payment page.
// Secrets: STRIPE_SECRET_KEY, PRICE_MONTHLY, PRICE_SEASON, SITE_URL (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are built in).
import Stripe from 'npm:stripe@18.0.0';
import { createClient } from 'npm:@supabase/supabase-js@2';

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY')!, { apiVersion: '2025-03-31.basil', httpClient: Stripe.createFetchHttpClient() });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  try {
    const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
    const token = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
    const { data: { user } } = await admin.auth.getUser(token);
    if (!user) return json({ error: 'Sign in first.' }, 401);

    const { plan } = await req.json().catch(() => ({}));
    const price = plan === 'monthly' ? Deno.env.get('PRICE_MONTHLY') : plan === 'season' ? Deno.env.get('PRICE_SEASON') : null;
    if (!price) return json({ error: 'Unknown plan.' }, 400);

    const { data: ent } = await admin.from('entitlements').select('stripe_customer_id, season_until, sub_until, status').eq('user_id', user.id).maybeSingle();
    const now = Date.now(), live = (t?: string | null) => !!t && Date.parse(t) > now;
    // don't sell what they already have: a season pass covers everything; an active monthly plan can still move up to the season pass
    if (live(ent?.season_until)) return json({ error: 'You already have the Season Pass.' }, 409);
    if (plan === 'monthly' && live(ent?.sub_until) && ent?.status !== 'canceled') return json({ error: 'You already have Pro Monthly.' }, 409);

    let customer = ent?.stripe_customer_id as string | undefined;
    if (!customer) {
      customer = (await stripe.customers.create({ email: user.email, metadata: { user_id: user.id } })).id;
      await admin.from('entitlements').upsert({ user_id: user.id, stripe_customer_id: customer }, { onConflict: 'user_id' });
    }

    const site = Deno.env.get('SITE_URL') || 'https://bennyspicks.us/';
    const session = await stripe.checkout.sessions.create({
      mode: plan === 'monthly' ? 'subscription' : 'payment',
      customer,
      client_reference_id: user.id,
      line_items: [{ price, quantity: 1 }],
      allow_promotion_codes: true,
      metadata: { user_id: user.id, plan },
      ...(plan === 'monthly' ? { subscription_data: { metadata: { user_id: user.id } } } : {}),
      success_url: new URL('?checkout=success#pro', site).toString(),
      cancel_url: new URL('?checkout=cancel#pro', site).toString(),
    });
    return json({ url: session.url });
  } catch (e) {
    console.error(e);
    return json({ error: 'Couldn’t start checkout. Try again in a moment.' }, 500);
  }
});
