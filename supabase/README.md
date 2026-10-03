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

## Updating the Supabase library

`index.html` loads a pinned version of `@supabase/supabase-js` from jsDelivr, checked with a hash (`SB_LIB`). To move to a newer version:

1. Change the version number in `SB_LIB.src`.
2. Recompute the hash and replace `SB_LIB.sri` with the result:

   ```sh
   curl -sL <new url> | openssl dgst -sha384 -binary | openssl base64 -A
   ```

   Put `sha384-` in front of the output.
