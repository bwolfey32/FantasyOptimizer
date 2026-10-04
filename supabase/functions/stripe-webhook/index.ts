// Stripe calls this after a payment or a subscription change; it is the only thing that grants or ends Pro.
// Deploy with "Enforce JWT verification" OFF: Stripe can't send a Supabase token, so the request is trusted only after its
// Stripe signature checks out. Events: checkout.session.completed, customer.subscription.updated, customer.subscription.deleted.
// Secrets: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, SEASON_END (e.g. 2027-02-28T23:59:59Z), and optionally POSTHOG_KEY
// (the site's public PostHog project key) to record confirmed payments in analytics.
import Stripe from 'npm:stripe@18.0.0';
import { createClient } from 'npm:@supabase/supabase-js@2';

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY')!, { apiVersion: '2025-03-31.basil', httpClient: Stripe.createFetchHttpClient() });
const crypto = Stripe.createSubtleCryptoProvider();
const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
const seasonEnd = () => new Date(Deno.env.get('SEASON_END') || '2027-02-28T23:59:59Z').toISOString();
const iso = (sec?: number | null) => (sec ? new Date(sec * 1000).toISOString() : null);

// newer Stripe API versions keep the billing period on the subscription's items
const periodEnd = (s: Stripe.Subscription) => (s as any).current_period_end ?? s.items?.data?.[0]?.current_period_end ?? null;

async function userFor(customer: string | null, hint?: string | null) {
  if (hint) return hint;
  if (!customer) return null;
  const { data } = await admin.from('entitlements').select('user_id').eq('stripe_customer_id', customer).maybeSingle();
  return data?.user_id ?? null;
}

// write the new dates, then pro_until = the later of the season pass and the monthly plan
async function save(userId: string, fields: Record<string, unknown>) {
  const { data: cur } = await admin.from('entitlements').select('season_until, sub_until').eq('user_id', userId).maybeSingle();
  const next = { ...cur, ...fields } as { season_until?: string | null; sub_until?: string | null };
  const s = next.season_until ? Date.parse(next.season_until) : 0, m = next.sub_until ? Date.parse(next.sub_until) : 0;
  const row = { user_id: userId, ...fields, pro_until: s || m ? new Date(Math.max(s, m)).toISOString() : null, plan: s || m ? (s >= m ? 'season' : 'monthly') : null };
  const { error } = await admin.from('entitlements').upsert(row, { onConflict: 'user_id' });
  if (error) throw error;
}

// Analytics: a paid or ended plan, under the account's internal id (the same id the site uses after sign-in; never the
// email). Best effort: a slow or failed PostHog call never fails the webhook.
async function track(userId: string, event: string, properties: Record<string, unknown>) {
  const key = Deno.env.get('POSTHOG_KEY'); if (!key) return;
  try {
    await fetch('https://us.i.posthog.com/i/v0/e/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(3000),
      body: JSON.stringify({ api_key: key, event, distinct_id: userId, properties: { ...properties, source: 'stripe_webhook' } }) });
  } catch (e) { console.error('analytics', e); }
}

function subFields(s: Stripe.Subscription) {
  const ok = ['active', 'trialing', 'past_due'].includes(s.status);
  // paid through the period end; a cancelled plan runs to when it ended; an unpaid or abandoned one gives nothing
  const until = s.ended_at ? iso(s.ended_at) : ok ? iso(periodEnd(s)) : new Date().toISOString();
  return { stripe_subscription_id: s.id, sub_until: until, status: s.cancel_at_period_end && ok ? 'canceling' : s.status };
}

Deno.serve(async (req) => {
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(await req.text(), req.headers.get('Stripe-Signature') || '', Deno.env.get('STRIPE_WEBHOOK_SECRET')!, undefined, crypto);
  } catch {
    return new Response('Bad signature', { status: 400 });
  }
  try {
    if (event.type === 'checkout.session.completed') {
      const s = event.data.object as Stripe.Checkout.Session;
      const customer = typeof s.customer === 'string' ? s.customer : s.customer?.id ?? null;
      const userId = await userFor(customer, s.client_reference_id || s.metadata?.user_id);
      if (!userId) return new Response('No user for this checkout', { status: 200 });
      if (s.mode === 'payment' && s.payment_status === 'paid') {
        await save(userId, { stripe_customer_id: customer, season_until: seasonEnd() });
        // moving up from monthly: stop the monthly plan at the end of what's already paid, so nobody pays twice
        const { data: cur } = await admin.from('entitlements').select('stripe_subscription_id').eq('user_id', userId).maybeSingle();
        if (cur?.stripe_subscription_id) {
          // the metadata tells the cancel-request event below that this ending is an upgrade, not churn
          const sub = await stripe.subscriptions.update(cur.stripe_subscription_id, { cancel_at_period_end: true, metadata: { ended_by: 'season_upgrade' } }).catch(() => null);
          if (sub) await save(userId, subFields(sub));
        }
        await track(userId, 'payment_confirmed', { plan: 'season', amount: (s.amount_total ?? 0) / 100, currency: s.currency, upgraded_from_monthly: !!cur?.stripe_subscription_id });
      } else if (s.mode === 'subscription' && s.subscription) {
        const sub = await stripe.subscriptions.retrieve(typeof s.subscription === 'string' ? s.subscription : s.subscription.id);
        await save(userId, { stripe_customer_id: customer, ...subFields(sub) });
        await track(userId, 'payment_confirmed', { plan: 'monthly', amount: (s.amount_total ?? 0) / 100, currency: s.currency });
      }
    } else if (event.type === 'customer.subscription.updated' || event.type === 'customer.subscription.deleted') {
      const sub = event.data.object as Stripe.Subscription;
      const customer = typeof sub.customer === 'string' ? sub.customer : sub.customer.id;
      const userId = await userFor(customer, sub.metadata?.user_id);
      if (userId) {
        await save(userId, subFields(sub));
        if (event.type === 'customer.subscription.deleted') await track(userId, 'subscription_ended', { plan: 'monthly' });
        else {
          // Churn on the day it's decided: Stripe sends updates for many reasons, so react only when cancelling was
          // switched on or off (the portal sets cancel_at_period_end; newer Stripe versions may set cancel_at instead).
          const prev = ((event.data as any).previous_attributes || {}) as Record<string, unknown>;
          if ('cancel_at_period_end' in prev || 'cancel_at' in prev) {
            const was = !!(('cancel_at_period_end' in prev ? prev.cancel_at_period_end : sub.cancel_at_period_end) || ('cancel_at' in prev ? prev.cancel_at : sub.cancel_at));
            const now = !!(sub.cancel_at_period_end || sub.cancel_at), end = sub.cancel_at || periodEnd(sub);
            const weeks = end ? Math.max(0, Math.round((end * 1000 - Date.now()) / (7 * 864e5))) : null;
            if (now && !was) await track(userId, 'subscription_cancel_requested', { plan: 'monthly', weeks_remaining: weeks, reason: sub.metadata?.ended_by === 'season_upgrade' ? 'upgraded_to_season' : 'cancelled' });
            else if (!now && was) await track(userId, 'subscription_cancel_reversed', { plan: 'monthly', weeks_remaining: weeks });
          }
        }
      }
    }
    return new Response('ok', { status: 200 });
  } catch (e) {
    console.error(e);
    return new Response('Webhook handler failed', { status: 500 });   // Stripe retries
  }
});
