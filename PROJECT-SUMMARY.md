# Kelston Actuation quote builder — project overview

## Why this exists

Kelston Actuation was using PandaDoc to create quotes and found it more
complicated than needed for straightforward jobs. This is a purpose-built
replacement: simple enough to use day-to-day, but shared across the team
rather than living in one person's browser.

## What it does

- **Product/part catalog** — store parts and services with standard prices,
  so quotes can be built by picking from the list instead of retyping
  everything each time.
- **Customer records** — company name, contact, email, phone, address,
  stored once and reused across quotes.
- **Quote builder** — pick a customer, add line items (from the catalog or
  typed freehand, including multi-line descriptions for specs/notes), and
  it auto-calculates subtotal, a discount %, VAT/tax %, and the total as you
  type.
- **Quote numbering** — assigned automatically and centrally, so two people
  creating quotes at the same time can never end up with duplicate numbers.
- **Print / PDF output** — a clean, branded one-page quote, generated from
  the browser's own "Print → Save as PDF," no extra software needed.
- **Dashboard** — pipeline value, accepted value, and a recent-quotes list
  by status (draft/sent/accepted/rejected/expired).
- **Team accounts** — each person logs in with their own email/password.
  Admins can add/remove teammates and edit company details (name, address,
  VAT rate, quote numbering prefix); regular members can create and manage
  products, customers, and quotes but not company settings or the team list.
- **Backups** — admins can download a full JSON export of all data at any
  time from within the app.
- Light/dark mode, works on desktop and mobile browsers.

## Who uses it and how

Everyone on the team gets their own login and sees the same shared data —
add a customer once, everyone can quote them; add a product once, everyone
prices it the same way.

## Current status

The application is fully built and has been tested end-to-end (account
setup, login, multi-user data sharing, permissions, quote creation and
printing). **What's outstanding is purely hosting/deployment** — getting it
running on a server with a public web address so the team can reach it.
Nothing about the app itself still needs building for a first version to go
live.

## Technical summary (for the developer)

- **Backend:** Python (Flask) + SQLite — no external database service to
  provision.
- **Frontend:** plain HTML/CSS/JS, no build step or framework tooling.
- **Packaged with a Dockerfile** — runs anywhere that accepts a Docker
  image (Railway, Render, Fly.io, a VPS, etc.). Railway is the intended
  target since an account is already set up, but it's not a hard
  requirement.
- **Needs:** a persistent volume/disk (SQLite database file must survive
  restarts and redeploys) and three environment variables (`SECRET_KEY`,
  `DATABASE_PATH`, `COOKIE_SECURE`).
- Full step-by-step deployment instructions, exact commands, and the
  source code are in the attached `kelston-quotes-server.zip` and
  `DEPLOYMENT-HANDOFF.md` — that's the document to hand the developer
  directly, this one is more "what and why" for your own reference or to
  set the scene before sharing the technical brief.

## Ongoing development

This was built by Claude (in an Anthropic Cowork session) and can keep
being extended the same way — new features, fixes, or design changes get
built and tested, then handed over as an updated project file. Once the
app is hosted (ideally via a GitHub repo connected to Railway so it
redeploys automatically), pushing an update becomes a lighter step than
this initial deployment was — the heavy lifting was getting it live the
first time.

## Estimated scope for a developer

Given the app is complete and containerized, deployment alone is roughly a
15–30 minute job for someone with basic Docker/hosting experience. See
`DEPLOYMENT-HANDOFF.md` for the exact steps.
