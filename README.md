# ABC-MIB Internal Training Survey Form

Streamlit + Supabase app for collecting and analyzing internal training feedback.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Supabase (Postgres) schema: tables, trigger, RLS policies |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml` | Supabase credentials template |
| `app.py` | The Streamlit application (auth, survey form, admin dashboard) |

## 1. Create the Supabase project

1. Go to [supabase.com](https://supabase.com) → **New Project**. Note the project's database password somewhere safe.
2. Once provisioned, open **Project Settings → API** and copy:
   - **Project URL**
   - **anon public** key
3. Open **Project Settings → Authentication → Providers → Email** and, for an internal-only tool, turn **off** "Confirm email" so new sign-ups can log in immediately. (Leave it on if you want email verification — see note below.)

## 2. Run the schema

1. In the Supabase dashboard, open **SQL Editor → New query**.
2. Paste the entire contents of `schema.sql` and click **Run**.
3. This creates `users_profile`, `survey_responses`, the auto-profile trigger, and all RLS policies. Every new sign-up automatically gets a `users_profile` row with `role = 'user'`.

## 3. Default admin account

`schema.sql` auto-promotes **`abc576887@gmail.com`** to `role = 'admin'` the moment it signs up (see the `admin_emails` array inside `handle_new_user()`), and also backfills that role if the account already existed. So:

1. Run the app (step 5) and use **Sign Up** with `abc576887@gmail.com` — you'll land straight on the Admin Dashboard, no manual SQL step needed.
2. To add more default admins later, add their email to the `admin_emails` array in `schema.sql` and re-run that `create or replace function` block (plus a backfill `update` if they already signed up — see section 4 of the file).
3. To promote a one-off account without editing the array, run:
   ```sql
   update public.users_profile set role = 'admin' where email = 'someone@abc-mib.com';
   ```

## 4. Configure secrets

Edit `.streamlit/secrets.toml`:

```toml
[supabase]
url = "https://YOUR_PROJECT_REF.supabase.co"
key = "YOUR_SUPABASE_ANON_PUBLIC_KEY"

[app]
company_name = "ABC-MIB Group Co., Ltd."
```

Use the **anon public** key only — never the `service_role` key in a Streamlit app, since `secrets.toml` / app code is not a safe place for a key that bypasses RLS.

## 5. Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL Streamlit prints (usually `http://localhost:8501`). Test on your phone by visiting your machine's LAN IP on the same network, e.g. `http://192.168.1.x:8501`, to confirm the mobile layout.

## 6. Deploy to Streamlit Community Cloud

1. Push this folder to a **private** GitHub repository (do not commit real secrets — the tracked `secrets.toml` should keep placeholder values only).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → pick the repo/branch → main file `app.py`.
3. In **Advanced settings → Secrets**, paste the real values:
   ```toml
   [supabase]
   url = "https://YOUR_PROJECT_REF.supabase.co"
   key = "YOUR_SUPABASE_ANON_PUBLIC_KEY"

   [app]
   company_name = "ABC-MIB Group Co., Ltd."
   ```
4. Deploy. Share the resulting URL with trainees (mobile) and admins (desktop).

## How access control works

- Every table has **Row Level Security** enabled. A regular user can only insert/read their **own** `survey_responses`; an admin (role check via `is_admin()`) can read/delete all of them.
- The Streamlit app itself just reflects this: it reads `users_profile.role` after login and routes to the survey form or the dashboard — but the real enforcement happens in Postgres via RLS, so even a modified client can't read other users' data.
- **Multi-user note:** the Supabase client is created fresh per browser session (`st.session_state`), not shared via `@st.cache_resource`. Streamlit Community Cloud serves all visitors from one process, so a shared, cached client would leak one user's auth session into another user's tab — this app avoids that deliberately.

## Known limitation

Streamlit's `st.session_state` doesn't survive a hard browser refresh (F5) — the user is logged out and must sign in again. This is acceptable for a survey tool; if persistent sessions across refreshes are needed later, add a small cookie component (e.g. `streamlit-cookies-controller`) to store the Supabase refresh token and restore the session with `supabase.auth.set_session()` on load.
