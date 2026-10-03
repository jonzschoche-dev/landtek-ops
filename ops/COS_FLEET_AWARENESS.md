# CoS Fleet Awareness

*Generated 2026-09-26 06:45 PhST by `scripts/cos_bridge.py --snapshot`.*

Enumeration spine: **`agent_registry`** (deploy_810). Cos owns `grok_bot` + `claude_subagent`; `fleet_registry` owns systemd/cron/catalog. Equilibrium: `--pulse` → `propagation_log` (seed_type=`fleet`, shadow) + `equilibrium_coverage_log` — see `docs/RELATIONSHIP_EQUILIBRIUM.md`.

## Stack effect rule (Jonathan / CoS)

Every CoS action must affect the stack, not chat memory alone:
- **assign / pause / re-own a desk** → upsert agent_registry via cos_bridge **and** enqueue a `work_orders` row (assignee = agent_key) + `--pulse`.
- **approve outward** → existing outward gates (A21/A26/S14); still ledger via pulse / propagation so related subjects get cued.
- **Discovery / research desks** → cue related matters through work_orders; do not rely on seat chat history as system of record.

## Layer A — grok_bot (Grok Bot seats)

| agent_key | display_name | owner | tier | note |
|---|---|---|---|---|
| `grok:cos` | Chief of Staff | governance | T0 | Grok Bot UUID 51390211-dd22-4b80-84db-82009924fe2c; charter agent_specs/006_mast |
| `grok:26-360` | Civil Case 26-360 MTC Mercedes | legal-strategy | T0 | Grok Bot UUID c51e50a8-b52e-4ecd-aafb-3ba5eb7de39c |
| `grok:1321` | ARTA CTN SL-2026-0209-1321 | forums | T0 | Grok Bot UUID 9ec27d0c-cce1-4410-894c-ecb29555e5bb |
| `grok:1378` | ARTA CTN SL-2026-0218-1378 | forums | T0 | Grok Bot UUID 796f1849-7c61-4707-8354-948ad154e949; 1378 BOT |
| `grok:op` | OP supervisory-review spine | forums | T0 | Grok Bot UUID afb5b1ca-9ffb-472d-987b-8bd971a0378c; OP BOT |
| `grok:guardianship` | Spec. Proc. 2680 RTC Br 41 Daet | legal-strategy | T0 | Grok Bot UUID 987e23b8-2192-493e-b94d-1661e3c2cea5 |
| `grok:mlgoo` | DILG/MLGOO Mercedes | forums | T0 | Grok Bot UUID 6dd731dc-5963-47be-b063-6ec9534ebe3d |
| `grok:provincial` | Provincial oversight | governance | T0 | Grok Bot UUID 28785974-9aa0-43a8-b137-9b9df6865d0b |
| `grok:inocalla` | Paracale-001 / Allan Inocalla | client-mgmt | T0 | Grok Bot UUID b1f19ae5-2b88-41db-9698-7edc8654e613 |
| `grok:formation` | LandTek Path C company standup | product | T0 | Grok Bot UUID 34930f30-4b9e-40b1-a23e-16dabe2229be; LandTek Formation |
| `grok:stack-inspector` | Stack architecture hygiene | governance | T0 | Grok Bot UUID 52914058-0585-4638-b7b6-ad37a25ff98b; Stack Inspector |
| `grok:floor` | LandTek Floor coordination | governance | T0 | Grok Bot UUID 74bfb675-7f3c-4337-ba4e-5269547de2a2; LandTek Floor |

## Layer B — claude_subagent

| agent_key | display_name | owner | role |
|---|---|---|---|
| `claude:case-26360-strategist` | CASE 26-360 STRATEGIST | legal-strategy | Use as the dedicated war-room desk for Civil Case 26-360 (Zschoche v. |
| `claude:mapping-agent` | Mapping Agent | mapping | Use for the property MAPPING subsystem — turning parcels into something a client can SEE and stand i |
| `claude:ombudsman-hunter` | Ombudsman Hunter | offense | Build client-isolated Ombudsman evidence leads and track agency referrals from the existing corpus. |
| `claude:product-hardener` | Product Hardener | product | Use for relentless reliability + correctness work on the existing LandTek stack — closing the "stack |
| `claude:revenue-engineer` | Revenue Engineer | revenue | Use for the money side of shipping LandTek — pricing + retainer packaging, per-matter ROI and the >8 |
| `claude:ship-packager` | Ship Packager | product | Use to turn LandTek's built capabilities into a client-VISIBLE, sellable deliverable — the workspace |
| `claude:truth-qa-gate` | Truth-QA Gate | governance | Use as the adversarial gate BEFORE anything reaches a paying client — briefs, demand letters, dossie |

## Runtime layers — systemd / cron / catalog (fleet_registry)

**DB unreachable from this host** (connection to server at "172.18.0.3", port 5432 failed: timeout expired
). File inventory for A+B is above. On VPS run `python3 scripts/fleet_registry.py --sync` then `python3 scripts/cos_bridge.py --sync --pulse` to populate runtime layers and ledger the fleet_change into the equilibrium spine.

## Layer notes

- **grok_bot**: Grok Bot chat seats (CoS can message). agent_key prefix grok:. Owned by cos_bridge.
- **claude_subagent**: Claude Code subagents under .claude/agents/. agent_key prefix claude:. Owned by cos_bridge.
- **systemd**: VPS landtek-*.timer units. Owned by fleet_registry.
- **cron**: VPS crontab scripts. Owned by fleet_registry.
- **cron-child**: refresh_all.py children. Owned by fleet_registry.
- **catalog-only**: agents.py on-demand tools with no runtime heartbeat. Owned by fleet_registry.

## Commands

```bash
# Mac (awareness + file snapshot)
python3 scripts/cos_bridge.py --snapshot
python3 scripts/cos_bridge.py --report
# VPS (DB + equilibrium ledger)
docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_980_cos_awareness_bridge.sql
python3 scripts/fleet_registry.py --sync
python3 scripts/cos_bridge.py --sync --pulse
```

