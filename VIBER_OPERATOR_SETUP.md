# VIBER CHANNEL SETUP — OPERATOR STEPS

**What's in place:** Viber webhook handler, channel bridge, dispatcher integration  
**What's needed:** Two operator actions to go live

---

## STEP 1: CREATE VIBER BOT & GET AUTH TOKEN

**On partners.viber.com:**

1. Sign in (or create account)
2. **Create Account** → Business Account
   - Account Name: "LandTek Legal" (or similar)
   - Account Icon: optional (professional logo)
   - Category: "Business Services"
3. **Go to Bots & API** → Create Bot
   - Bot Name: "LandTek Leo"
   - Description: "Autonomous legal case management"
4. **Copy the Auth Token** (64-char hex string)
   - Looks like: `445da6az1s312a30s2a4s0a1b==`

**Save to `.env` on VPS:**

```bash
# On VPS, edit /root/landtek/.env
VIBER_AUTH_TOKEN=445da6az1s312a30s2a4s0a1b==
```

**Test the token:**

```bash
curl -X GET https://chatapi.viber.com/pa/account/info \
  -H "X-Viber-Auth-Token: 445da6az1s312a30s2a4s0a1b=="
```

**Expected response:**
```json
{
  "status": 0,
  "status_message": "ok",
  "id": "account_id_12345",
  "name": "LandTek Leo",
  "uri": "landtek-leo",
  "icon": "..."
}
```

---

## STEP 2: EXPOSE LEO-TOOLS & REGISTER WEBHOOK

**Problem:** leo-tools runs on `localhost:8765` (Tailscale private). Viber needs a public HTTPS URL.

**Solution: Pick one**

### Option A: Cloudflare Tunnel (Recommended for reliability)

```bash
# 1. Install cloudflared (on VPS)
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# 2. Authenticate
cloudflared tunnel login
# (opens browser, authenticate with Cloudflare account)

# 3. Create tunnel
cloudflared tunnel create landtek-leo

# 4. Route traffic
cloudflared tunnel route dns landtek-leo landtek.example.com
# (or use your domain)

# 5. Run tunnel (background)
cloudflared tunnel run landtek-leo \
  --url http://localhost:8765 \
  --hostname landtek-leo.example.com &

# Public URL: https://landtek-leo.example.com
```

### Option B: ngrok (Quick, temporary)

```bash
# 1. Download ngrok from ngrok.com, extract, auth
ngrok config add-authtoken <your_token>

# 2. Expose leo-tools
ngrok http 8765

# Public URL: https://abc123def456.ngrok.io
# (changes each restart; save to .env)
```

### Option C: Domain + TLS Proxy (Production)

```bash
# 1. Own a domain (landtek-leo.com or similar)
# 2. Point DNS A record to VPS IP
# 3. Install cert (Let's Encrypt):
sudo certbot certonly --standalone -d landtek-leo.com

# 4. Run nginx reverse proxy
sudo systemctl start nginx
# (config in /etc/nginx/sites-available/landtek-leo)

# Public URL: https://landtek-leo.com
```

---

## STEP 3: REGISTER WEBHOOK WITH VIBER

**Once you have a public HTTPS URL**, register it with Viber:

```bash
# Save to .env (on VPS)
VIBER_WEBHOOK_URL=https://landtek-leo.example.com/api/channel/viber

# Run registration script
python3 /root/landtek/leo_tools/channels/viber_set_webhook.py \
  --set https://landtek-leo.example.com/api/channel/viber
```

**Expected output:**
```
✓ Webhook registered
  URL: https://landtek-leo.example.com/api/channel/viber
  Status: active
  Events: message, delivered, seen, failed
```

**Verify:**

```bash
curl -X GET https://chatapi.viber.com/pa/account/get_webhook \
  -H "X-Viber-Auth-Token: 445da6az1s312a30s2a4s0a1b=="
```

**Expected response:**
```json
{
  "status": 0,
  "webhook_url": "https://landtek-leo.example.com/api/channel/viber",
  "events": ["message", "delivered", "seen", "failed"]
}
```

---

## STEP 4: TEST END-TO-END

**Send a message to the Viber Bot (from your phone):**

1. Add bot to your contacts: search "LandTek Leo" on Viber
2. Send a test message: "Hello Leo"
3. Check Leo logs:

```bash
tail -f /root/landtek/leo_tools/leo.log | grep -i viber
```

**Expected:**
```
2026-06-21 15:30:45 [VIBER] Message from user_abc: "Hello Leo"
2026-06-21 15:30:46 [VIBER] Routing to Leo dispatcher
2026-06-21 15:30:47 [LEO] Response: "I'm Leo. What can I help with?"
2026-06-21 15:30:47 [VIBER] Sent reply via Viber PA API
```

---

## TROUBLESHOOTING

| Issue | Diagnosis | Fix |
|---|---|---|
| "Invalid signature" errors | Webhook auth token mismatch | Check VIBER_AUTH_TOKEN in .env matches partners.viber.com |
| Webhook not firing | URL not registered or unreachable | Run `viber_set_webhook.py --set` again; test URL with curl |
| 403 Forbidden on public URL | TLS cert issue or firewall | Check cert valid (openssl s_client), check VPS firewall |
| Leo not responding | Dispatcher not wired | Check `/api/channel/send` includes viber handler |
| Messages queue but don't send | No auth token in .env | Add VIBER_AUTH_TOKEN, restart leo-tools service |

---

## OPERATOR COMMANDS (Via Viber)

Once live, Jonathan can message Leo on Viber:

```
Jonathan: What's the status of CV-26360?
Leo: [Latest alerts + execution status]

Jonathan: Draft opposition
Leo: [Generates draft, asks for approval]

Jonathan: Approve
Leo: [Files with RTC, confirms in docket]

Jonathan: Show me deadlines
Leo: [Lists SoL dates, countdown to Aug 12]
```

---

## PRODUCTION CHECKLIST

- [ ] Create Viber Bot at partners.viber.com
- [ ] Copy auth token to `.env` as `VIBER_AUTH_TOKEN`
- [ ] Test token with account info API call
- [ ] Expose leo-tools publicly (Cloudflare / ngrok / domain)
- [ ] Save public URL to `.env` as `VIBER_WEBHOOK_URL`
- [ ] Run `viber_set_webhook.py --set <URL>`
- [ ] Verify webhook registered (`get_webhook` API call)
- [ ] Send test message from phone
- [ ] Confirm Leo responds via Viber
- [ ] Monitor logs for 24h (no errors)

---

**Two operator steps. Viber is live.**

