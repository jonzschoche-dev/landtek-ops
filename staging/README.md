# LandTek staging environment

On-demand n8n + Postgres stack that mirrors prod. Same VPS, different
containers/ports/volumes, **same encryption key** (so credentials in
restored pg_dumps decrypt correctly).

## Lifecycle

```bash
./start-staging.sh    # restore latest prod pg_dump, bring up
# ...test stuff against http://127.0.0.1:5679 or staging.leo.hayuma.org...
./stop-staging.sh     # bring down (keeps staging DB so you can pick up later)

./stop-staging.sh --wipe-volumes  # nuke staging state entirely
./start-staging.sh --no-restore   # bring up with existing staging DB intact
```

When staging is **down**: zero RAM/CPU overhead — prod runs alone.
When staging is **up**:    ~500 MB extra RAM (mostly swap-able at idle).

## Promotion workflow (testing a deploy)

1. `./start-staging.sh` — staging now has yesterday's prod state
2. Edit your `apply_deploy_NNN.py` to target staging:
   - point at staging postgres (port 5433) or set `LANDTEK_ENV=staging`
3. Run the deploy script — it patches the staging workflow
4. Trigger your test cases:
   - if it's a Telegram-triggered flow: temporarily point bot webhook at
     `https://staging.leo.hayuma.org/webhook/...` (or use the n8n editor's
     "Execute step" button to fire it manually)
5. **Green?** Re-run the same `apply_deploy_NNN.py` against prod.
6. **Red?** Iterate. Throw it away with `./stop-staging.sh --wipe-volumes`.

## Public access (optional)

Two steps to make `https://staging.leo.hayuma.org` work from the
internet:

1. **DNS:** add an `A` record `staging.leo.hayuma.org` → same IP as
   `leo.hayuma.org` (in your DNS provider).
2. **nginx + cert:** the nginx vhost is at
   `/etc/nginx/sites-available/leo-staging` (disabled by default).
   Enable with:
   ```bash
   ln -s /etc/nginx/sites-available/leo-staging /etc/nginx/sites-enabled/
   certbot --nginx -d staging.leo.hayuma.org
   nginx -t && systemctl reload nginx
   ```

Until then, access n8n via `ssh -L 5679:127.0.0.1:5679 vps` and browse
http://localhost:5679 locally.

## Watch out for

- **Telegram bot token is shared.** If you trigger a flow on staging
  that sends a Telegram message, it goes to the SAME chat as prod.
  Workflows should check `process.env.LANDTEK_ENV === 'staging'` and
  short-circuit external side-effects, OR comment them out in the
  staging workflow before testing.
- **Google Drive credential is shared.** A staging upload writes to the
  real MWK-001 folder. Same mitigation.
- **Cron triggers fire in staging too.** When staging is up, any
  scheduled workflows will also run there. If that matters, disable
  them in the staging editor after restore.
- **n8n version drift.** Both prod and staging pull `n8nio/n8n:latest`.
  If you want guaranteed parity, pin both to a specific tag.
