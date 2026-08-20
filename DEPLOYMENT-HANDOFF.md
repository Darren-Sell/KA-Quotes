# Deployment brief — Kelston Actuation quote builder

**Scope of this job:** the application is fully built and tested. What's needed is
just to get it deployed to Railway (hosting is already set up, just needs the
app pushed to it) and confirm it works. Should take about 15–30 minutes for
someone comfortable with Docker/basic hosting.

**Contact:** Darren, darren@kelstonactuation.com — he has a Railway account
already created but needs help getting the code deployed to it.

## What this is

A small self-contained web app: Python (Flask) backend + SQLite database +
a plain HTML/CSS/JS frontend, packaged with a `Dockerfile`. No build step,
no external services beyond the host itself. Source is in the attached
`kelston-quotes-server.zip`.

```
kelston-quotes-server/
├── Dockerfile
├── requirements.txt
├── server.py
├── app/            — Flask routes, auth, SQLite schema
├── static/         — index.html, styles.css, app.js (frontend)
└── README.md       — fuller technical notes, also covers Render/VPS as alternatives
```

## What's needed

Get this deployed to Railway under Darren's existing account, with:

1. A persistent volume so the SQLite database isn't wiped on redeploy.
2. Three environment variables set.
3. A public HTTPS domain generated.
4. Confirmation that visiting the domain shows the app's first-run "Set up
   your quote workspace" screen (i.e. the container is healthy and the app
   boots correctly).

## Suggested fastest path — Railway CLI, no GitHub needed

```bash
npm install -g @railway/cli      # or: brew install railway (macOS)
railway login                    # authorize against Darren's account
cd kelston-quotes-server
railway init                     # name it e.g. "kelston-quotes"
railway up                       # builds from the Dockerfile and deploys
```

Then in the Railway dashboard for that service:

- **Settings → Volumes** → add a volume, mount path `/data`
- **Variables** → add:
  - `SECRET_KEY` — any long random string, e.g. generate with
    `python3 -c "import secrets; print(secrets.token_hex(32))"`
  - `DATABASE_PATH` = `/data/app.db`
  - `COOKIE_SECURE` = `1`
- Redeploy after adding the volume/variables if it doesn't happen automatically.
- **Settings → Networking → Generate Domain**

Alternative path (GitHub → Railway "Deploy from repo") is also fine if you
prefer that workflow — Railway will auto-detect the `Dockerfile` either way.
Full details, including Render and self-hosted VPS/Docker instructions, are
in the `README.md` inside the zip.

## Handover back to Darren

Once it's live:

1. Send Darren the final domain URL (`https://....up.railway.app` or a
   custom domain if you set one up).
2. He'll open it and go through the first-run setup screen himself to create
   his own admin login (no credentials need to be shared with anyone —
   that screen only appears once, the very first time the empty database
   is used).
3. If you have a moment, consider adding Darren as a member on the Railway
   project itself (**Project Settings → Members**) so he can see
   logs/billing/manage the volume going forward without depending on you.

Any questions on the app's behavior (not the deploy mechanics), the
`README.md` in the zip has more detail, including how team member accounts
and company settings work once it's running.
