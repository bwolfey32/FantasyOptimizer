# Setting up accounts

Accounts let people sign in on any device and see their teams and past lineups there. They run on [Supabase](https://supabase.com)'s free tier. Until the steps below are done, `CLOUD` in `index.html` stays empty, the **Sign in** button stays hidden, and the site works exactly as before.

You only do this once. It takes about 20 minutes.

## 1. Create the project

1. Sign up at supabase.com, then press **New project**. Any name works (for example `bennys-picks`). Pick the region closest to most users and save the database password somewhere safe; the site never needs it.
2. When the project is ready, open **SQL Editor**, paste in all of [`schema.sql`](schema.sql), and press **Run**. This creates the two tables, the rules that let each person see only their own rows, and the delete-account function.

## 2. Tell Supabase where the site lives

**Authentication → URL Configuration:**

- **Site URL:** `https://bennyspicks.us/`
- **Redirect URLs:** add `https://bennyspicks.us/` and, for local testing, `http://localhost:8000/**`

## 3. Send a code instead of a link

Sign-in by email uses a code people type in. Links are a poor fit on phones: they open in the mail app's own browser, and the person ends up signed in there instead of where they started.

**Authentication → Emails → Templates.** Change both **Magic link** and **Confirm signup** so the email shows the code. For example:

```html
<h2>Your Benny's Picks code</h2>
<p>Enter this code to sign in:</p>
<p style="font-size:28px;font-weight:700;letter-spacing:4px">{{ .Token }}</p>
<p>It expires in an hour. If you didn't ask for it, ignore this email.</p>
```

New users get **Confirm signup** and returning users get **Magic link**, so both need the code.

## 4. Turn on Google sign-in

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one).
2. Go to **APIs & Services → OAuth consent screen**. Choose **External** and fill in the app name (Benny's Picks), your support email and the site's address, then publish it.
3. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID** and choose **Web application**.
   - **Authorized JavaScript origins:** `https://bennyspicks.us`
   - **Authorized redirect URIs:** `https://<your-project-ref>.supabase.co/auth/v1/callback`. The exact address is shown in Supabase under **Authentication → Sign In / Providers → Google**.
4. Copy the client ID and client secret into Supabase (**Authentication → Sign In / Providers → Google**), turn the provider on, and save.

## 5. Send email through your own mail service (recommended)

Supabase's built-in email sender allows only a few emails an hour, which is fine for testing but not for real use. Under **Authentication → Emails → SMTP Settings**, connect a mail service. Resend, Postmark and Amazon SES all work, and Resend's free tier covers a hobby site.

## 6. Connect the site

1. In Supabase, open **Project Settings → API Keys** and copy the **publishable** key (it starts with `sb_publishable_`; the older "anon" key also works). Then copy the project URL (`https://<ref>.supabase.co`).
2. In `index.html`, fill in:

   ```js
   const CLOUD = { url: 'https://<ref>.supabase.co', key: 'sb_publishable_…' };
   ```

   The publishable key is meant to be public. Each person reaches only their own rows, because of the rules in `schema.sql`. **Never put the secret (service-role) key in the page.**
3. Commit and push. The **Sign in** button appears next to Settings.

## Checking it works

- **Sign in on two devices.** Sign in with your email on a computer and add a player. Sign in on your phone with the same email: the team is there. Change something on the phone, switch back to the computer's tab, and the change shows up within a few seconds.
- **Rows are private.** In Supabase, open **Table Editor → user_state**. There is one row per person. Signed in as a different person, a request for someone else's row returns nothing.
- **Delete account.** Delete a test account from **Account → Delete account**. Its row disappears from both tables and from **Authentication → Users**.

# Setting up Pro payments (Stripe)

Pro ($4.99/month, or $14.99 for the season) runs on Stripe. Three small server functions live in Supabase (`functions/`):
- **`checkout`** starts a payment;
- **`stripe-webhook`** is the only thing that grants or ends Pro, and only after Stripe's signature checks out;
- **`billing-portal`** lets monthly members cancel or change their card.

Until these steps are done, the **Go Pro** buttons show an error and nobody can be charged. Do everything in **test mode** first. It takes about 30 minutes.

## 1. Stripe account and products

1. Sign up at [stripe.com](https://stripe.com) and stay in **Test mode** (the toggle at the top).
2. Go to **Product catalog → Add product** and add two products:
   - **Benny's Picks Pro Monthly**: price $4.99, **Recurring**, monthly.
   - **Benny's Picks Pro Season Pass**: price $14.99, **One-off**.
3. Open each product and copy its **price ID** (it starts with `price_`).
4. **Settings → Billing → Customer portal:** turn it on and allow customers to cancel subscriptions and update payment methods.
5. Optional: **Stripe Tax** works out and collects US sales tax for an extra 0.5% per transaction. If you skip it, you're responsible for any sales tax yourself.

## 2. Database

In Supabase, open **SQL Editor** and run the whole of [`schema.sql`](schema.sql) again. It's safe to re-run, and it adds the `entitlements` table, which records who has Pro and until when. People can read only their own row, and nobody can write it from the website.

## 3. The three functions

For each folder in `functions/` (`checkout`, `stripe-webhook`, `billing-portal`):
1. Go to **Edge Functions → Deploy a new function → Via editor**.
2. Name it exactly like the folder.
3. Paste in that folder's `index.ts` and deploy.

Then open **stripe-webhook → Details** and turn **Enforce JWT verification** **off**. Stripe can't send a Supabase sign-in token, so the function checks Stripe's signature instead. Leave it on for the other two.

## 4. Secrets

**Edge Functions → Secrets.** Add these:

| Name | Value |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe → Developers → API keys → **Secret key** (`sk_test_…`) |
| `PRICE_MONTHLY` | the monthly price ID (`price_…`) |
| `PRICE_SEASON` | the season pass price ID |
| `SEASON_END` | `2027-02-28T23:59:59Z`, when this season's pass ends. Change it each season, together with `SEASON_END_LABEL` in `index.html`. |
| `SITE_URL` | `https://bennyspicks.us/` |
| `STRIPE_WEBHOOK_SECRET` | from step 5 |
| `POSTHOG_KEY` | optional: the site's PostHog project key (`phc_…`, the same public key as `PH.key` in `index.html`), so `stripe-webhook` records confirmed payments in analytics |

## 5. The webhook

1. In Stripe, go to **Developers → Webhooks → Add endpoint**.
2. Set the **Endpoint URL** to `https://<your-project-ref>.supabase.co/functions/v1/stripe-webhook`.
3. Under **Events**, select `checkout.session.completed`, `customer.subscription.updated` and `customer.subscription.deleted`.
4. Save, then copy the endpoint's **Signing secret** (`whsec_…`) into the `STRIPE_WEBHOOK_SECRET` secret above.

## 6. Test it

1. On the site, sign in, open **Pro**, and press **Get the Season Pass**. On Stripe's page, pay with the test card `4242 4242 4242 4242` (any future date, any CVC).
2. Back on the site, "Activating Pro…" turns into "Welcome to Pro". The ads disappear and every recommendation unlocks. In Supabase, **Table Editor → entitlements** shows your row with `plan = season`.
3. With a second test account, buy **Monthly**. Then go to **Account → Manage billing** and cancel. Pro stays on until the end of the month, and the account panel says "ends …".
4. In Stripe, **Webhooks → your endpoint** should show every event delivered with status 200.

## 7. Go live

Switch Stripe to **Live mode** and recreate the two products there; live and test products are separate. Then, in Supabase:
- update `STRIPE_SECRET_KEY` (`sk_live_…`), `PRICE_MONTHLY` and `PRICE_SEASON`;
- add a live-mode webhook endpoint the same way, and update `STRIPE_WEBHOOK_SECRET` with its new signing secret.

Before taking real payments, fill in the bracketed parts of `privacy.html` and `terms.html`: your name, a contact email and the refund policy.

## Each new season

1. Update `SEASON_END` in Supabase and `SEASON_END_LABEL` in `index.html`.
2. If the season pass price changes, update the Stripe price, the `PRICE_SEASON` secret and `PRO_PRICE` in `index.html`.

# Ads (Google AdSense)

Free users see one ad on research-style pages: Waivers, Start / Sit, Research and Roster. Until AdSense approves the site, that slot shows Benny's own Pro promotions.
1. Apply at [adsense.google.com](https://adsense.google.com) with `bennyspicks.us`. The privacy policy and terms pages are already linked in the site's footer.
2. In AdSense, turn on **Privacy & messaging → European regulations** (Google's consent message for EU/UK visitors).
3. Once you're approved, create a **Display ad** unit and send me the publisher ID (`ca-pub-…`) and the ad unit's slot ID. I'll fill in `ADS` in `index.html` and add the `ads.txt` file Google asks for.

## Updating the Supabase library

`index.html` loads a pinned version of `@supabase/supabase-js` from jsDelivr, checked with a hash (`SB_LIB`). To move to a newer version:

1. Change the version number in `SB_LIB.src`.
2. Recompute the hash and replace `SB_LIB.sri` with the result:

   ```sh
   curl -sL <new url> | openssl dgst -sha384 -binary | openssl base64 -A
   ```

   Put `sha384-` in front of the output.
