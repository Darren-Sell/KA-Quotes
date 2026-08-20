# Kelston Actuation — Quote Builder (shared server version)

A small multi-user quote builder: a shared product catalog, customer list, and
quote history that your whole team logs into and sees the same data in.
Replaces the single-browser-tab version that only one person could use at a time.

- Backend: Python + Flask + SQLite (no external database to set up)
- Auth: individual email/password logins, admin vs. member roles
- Frontend: plain HTML/CSS/JS, no build step

## What each person can do

- **Admins** — everything members can do, plus: add/remove team members,
  edit company details (name, address, VAT rate, quote numbering), download
  a full JSON backup.
- **Members** — create/edit/delete products, customers, and quotes; change
  their own password.

## Deploying to Railway (recommended)

Railway is a simple place to run this for a small team — around $5/mo,
no server administration.

1. **Get the code into a git repo.** Unzip this project, then from inside
   the folder:
   ```
   git init && git add -A && git commit -m "Initial commit"
   ```
   Push it to a new GitHub repo (or use `railway up` in step 3, which can
   deploy straight from your local folder without GitHub at all).

2. **Create a Railway account and project** at [railway.com](https://railway.com),
   then either "Deploy from GitHub repo" (pick the repo you just pushed) or
   install the CLI (`npm i -g @railway/cli`, then `railway login`).

3. **Deploy:**
   - Via GitHub: Railway detects the `Dockerfile` automatically and builds it.
   - Via CLI, from inside the project folder: `railway init` then `railway up`.

4. **Add a persistent volume** (critical — without this, your data is wiped
   on every redeploy): in the Railway dashboard, open your service →
   **Settings → Volumes** → add a volume → mount path `/data`.

5. **Set environment variables** under **Variables**:
   - `SECRET_KEY` — generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_PATH` = `/data/app.db`
   - `COOKIE_SECURE` = `1`

6. **Generate a public domain**: Settings → Networking → "Generate Domain".
   Railway provides HTTPS automatically.

7. Visit the domain — you'll land on the first-run setup screen. Create your
   admin account, then add teammates from the **Team** tab.

### Alternative: Render

Same idea — push to GitHub, create a new **Web Service** from the repo,
Render will detect the Dockerfile. Add a **persistent disk** mounted at
`/data` (Render calls this a "Disk", available on paid instance types), and
set the same three environment variables as above.

### Alternative: your own server / VPS

```
docker build -t kelston-quotes .
docker run -d -p 8080:8080 \
  -v /some/persistent/path/on/host:/data \
  -e SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  -e DATABASE_PATH=/data/app.db \
  -e COOKIE_SECURE=1 \
  --name kelston-quotes \
  kelston-quotes
```
Put a reverse proxy (Caddy, nginx, or Cloudflare Tunnel) in front for HTTPS —
browsers require a secure connection for login cookies to work reliably
outside of localhost.

## Running it locally (for testing/development)

Requires Python 3.11+ with `pip install -r requirements.txt` (needs internet
access to fetch Flask/PyJWT/gunicorn — most personal machines will have this
even though it wasn't available inside the sandbox this was built in).

```
pip install -r requirements.txt
export SECRET_KEY=dev-secret
export COOKIE_SECURE=0   # only for plain http:// on localhost
python3 server.py
```
Then open http://localhost:8080.

## Backups

Admins can click **Export backup** in the top bar at any time to download a
JSON snapshot of every product, customer, and quote. Keep the underlying
`/data` volume backed up too if your host supports snapshotting it directly
(Railway volumes are backed up as part of your project; on a VPS, back up
the mounted host directory).

## Notes on scale

This is built for a small internal team (a handful of concurrent users),
which is what was asked for. SQLite handles that comfortably. If this grows
into dozens of simultaneous users or you want real-time sync across
sessions, that's the point to move to a hosted Postgres database — the code
is organised so that's a contained change (everything goes through
`app/db.py`).
