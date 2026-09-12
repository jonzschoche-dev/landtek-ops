#!/usr/bin/env python3
"""Illustrative scenario models per wave for the partner memo — NOT forecasts.
Every input is listed with its status (sourced / assumption). Change an input, re-run, and the annex
regenerates between the ANNEX-A markers in MEMO_STEPHEN_JULIET_MINING_OPPORTUNITY_2026-09.md.
Usage: python3 opportunity_projections.py            (rewrites the annex in the memo)
"""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
MEMO = os.path.join(HERE, "MEMO_STEPHEN_JULIET_MINING_OPPORTUNITY_2026-09.md")

# ---------------- market inputs (dated; sourced) ----------------
GOLD_USD_OZ = 4362.0        # spot, 11 Sep 2026 (Kitco/USAGOLD/JM Bullion, ~4,361–4,386)
USD_PHP     = 62.60         # BSP reference rate, 8 Sep 2026
G_PER_OZ    = 31.1035
PHP_PER_G   = GOLD_USD_OZ * USD_PHP / G_PER_OZ
BSP_HAIRCUT = 0.01          # assumption: BSP buys at ~world price less ~1% (charges); confirm with BSP schedule
DAYS        = 25            # assumption: operating days per month

def scen(low, base, high): return {"Low": low, "Base": base, "High": high}
K = ("Low", "Base", "High")

# ---------------- Wave 1 — MFPS activation (Casalugan), from ~month 4 after funding ----------------
W1 = dict(
    tpd      = scen(3.5, 7.0, 10.0),      # 3.5 = reported current circuit rate; 10 = LAB X target
    grade    = scen(2.0, 3.5, 5.0),       # g/t delivered ore — ASSUMPTION (no assays on file; Benguet-era vein figures unverified)
    recovery = scen(0.50, 0.60, 0.70),    # mercury-free gravity circuit — ASSUMPTION until the GRG test
    share    = scen(0.25, 0.35, 0.45),    # treatment margin retained by the plant under ore-supply/toll terms — PLACEHOLDER, to be negotiated
    opex_t   = scen(1500, 1200, 1000),    # ₱/t plant operating cost (power, labour, consumables, maintenance) — ASSUMPTION
    fixed    = scen(300_000, 250_000, 200_000),  # ₱/month overhead — ASSUMPTION
)
# ---------------- Wave 2 — AVI Gold Processing (Jose Panganiban), from ~month 12–18 ----------------
W2 = dict(
    tpd      = scen(10.0, 25.0, 50.0),    # 50 = Gracesen ECC precedent (crusher + mill rated 50 t/d)
    grade    = scen(2.0, 3.5, 5.0),
    recovery = scen(0.55, 0.70, 0.88),    # gravity-only (Low) → gravity + leach (High; needs cyanide/hazwaste/air permits)
    share    = scen(0.35, 0.45, 0.55),    # own Minahang Bayan, integrated — PLACEHOLDER
    opex_t   = scen(1500, 1800, 2200),    # rises with the leach option (reagents) — ASSUMPTION
    fixed    = scen(500_000, 600_000, 750_000),
    capex    = scen(15e6, 35e6, 60e6),    # ₱ plant build — ASSUMPTION, no quotes (the ₱29M MFPS is a donor-built ~3.5 tpd benchmark)
    permits  = scen(1.5e6, 2.5e6, 4e6),   # ₱ ECC/WDP/CCO/LGU/DAR — ASSUMPTION
)
# ---------------- Wave 3 — exploration earn-in (no production; spend only) ----------------
W3 = dict(  # C$ — ASSUMPTIONS typical of a junior program; Phases per the 36-month plan
    phase1 = scen(0.3e6, 0.45e6, 0.6e6),   # baseline & access, shaft inventory, MOA, MB petition (months 1–6)
    phase2 = scen(0.8e6, 1.1e6, 1.5e6),    # underground mapping & sampling (months 7–18)
    drill_m = scen(3000, 5000, 8000),      # metres, targeted diamond drilling (months 19–36)
    drill_cost = scen(180, 200, 220),      # C$/m all-in — ASSUMPTION
    listing = scen(0.4e6, 0.6e6, 0.8e6),   # CPC/IPO all-in: legal, audit, QP report, exchange fees — ASSUMPTION
)
TSXV_MIN_PHASE1 = 200_000  # C$ — Policy 2.1 Tier 2 Mining minimum initial-phase program
CIT = 0.25                 # PH corporate income tax (20% may apply to small corporations) — note only
PGC = 0.40                 # PGC's maximum equity in the Philippine operating company

def php(x):
    if abs(x) >= 1e6: return f"₱{x/1e6:,.1f}M"
    return f"₱{x:,.0f}"
def cad(x): return f"C${x/1e6:,.2f}M" if abs(x) >= 1e5 else f"C${x:,.0f}"

def plant(W):
    out = {}
    for k in K:
        t_m = W["tpd"][k] * DAYS
        au_g = t_m * W["grade"][k] * W["recovery"][k]
        value = au_g * PHP_PER_G * (1 - BSP_HAIRCUT)
        gross = value * W["share"][k]
        net = gross - W["opex_t"][k] * t_m - W["fixed"][k]
        out[k] = dict(t_m=t_m, au_g=au_g, value=value, gross=gross, net=net,
                      net_after_tax=net * (1 - CIT) if net > 0 else net,
                      pgc=net * (1 - CIT) * PGC if net > 0 else 0)
    return out

def row(label, vals, fmt=lambda v: str(v)): return f"| {label} | " + " | ".join(fmt(vals[k]) for k in K) + " |"

def annex():
    r1, r2 = plant(W1), plant(W2)
    L = []
    L.append("## Annex A — Illustrative scenarios by wave (planning arithmetic, not forecasts)")
    L.append("")
    L.append("> **How to read this annex.** These are scenario calculations, not projections we assert. Every input is listed with its status; the ones marked *assumption* or *placeholder* have no quote, assay, test or agreement behind them yet, and the ones marked *placeholder* are exactly the commercial terms this memo says are negotiated separately. The arithmetic is reproducible (a script regenerates this annex from the inputs), so any partner can change an input and see the result. Nothing here is a mineral resource, a production forecast or an economic analysis in the NI 43-101 sense, and none of it may be used in any listing document until a Qualified Person's report exists. Gold at " + f"US${GOLD_USD_OZ:,.0f}/oz (11 Sep 2026) and ₱{USD_PHP:.2f}/US$ (BSP reference, 8 Sep 2026) give **₱{PHP_PER_G:,.0f} per gram**; the BSP buying price is taken as world price less ~{BSP_HAIRCUT:.0%} (to confirm).")
    L.append("")
    # Wave 1
    L.append("### A1. Wave 1 — MFPS activation, Casalugan (monthly, once the plant is running)")
    L.append("")
    L.append("| Input | Low | Base | High | Status |")
    L.append("|---|---|---|---|---|")
    L.append(row("Throughput, tonnes/day", W1["tpd"], lambda v: f"{v:g}") + " reported current circuit ≈ 3.5 t/d; 10 t/d = LAB X target |")
    L.append(row("Operating days/month", scen(DAYS, DAYS, DAYS)) + " assumption |")
    L.append(row("Head grade of delivered ore, g/t", W1["grade"], lambda v: f"{v:g}") + " **assumption** — no assays on file |")
    L.append(row("Gravity recovery", W1["recovery"], lambda v: f"{v:.0%}") + " **assumption** — set by the GRG test |")
    L.append(row("Treatment margin retained by plant", W1["share"], lambda v: f"{v:.0%}") + " **placeholder** — negotiated separately |")
    L.append(row("Plant operating cost, ₱/t", W1["opex_t"], lambda v: f"{v:,.0f}") + " assumption |")
    L.append(row("Fixed overhead, ₱/month", W1["fixed"], php) + " assumption |")
    L.append("")
    L.append("| Result (per month) | Low | Base | High |")
    L.append("|---|---|---|---|")
    L.append(row("Ore treated, t", {k: r1[k]["t_m"] for k in K}, lambda v: f"{v:,.0f}"))
    L.append(row("Gold recovered, g", {k: r1[k]["au_g"] for k in K}, lambda v: f"{v:,.0f}"))
    L.append(row("Value of recovered gold at BSP", {k: r1[k]["value"] for k in K}, php))
    L.append(row("Plant gross (its retained margin)", {k: r1[k]["gross"] for k in K}, php))
    L.append(row("Plant net before tax", {k: r1[k]["net"] for k in K}, php))
    L.append(row(f"PGC's {PGC:.0%} of net after {CIT:.0%} tax (if declared)", {k: r1[k]["pgc"] for k in K}, php))
    L.append("")
    L.append(f"Known Wave-1 numbers on file, not scenarios: the ₱5,000,000 financing returns ₱5.75M or ₱6.5M within six months depending on the 30% basis; the LAB X table costs ₱177–306k plus pad and utilities, unquoted. The Low case shows the point: at today's reported circuit rate and a thin plant margin, the plant roughly covers itself — the money is in throughput (LAB X) and recovery (the ore test), which is why those are the first two Wave-1 actions.")
    L.append("")
    # Wave 2
    L.append("### A2. Wave 2 — AVI Gold Processing, Jose Panganiban (monthly, at steady state)")
    L.append("")
    L.append("| Input | Low | Base | High | Status |")
    L.append("|---|---|---|---|---|")
    L.append(row("Throughput, tonnes/day", W2["tpd"], lambda v: f"{v:g}") + " 50 t/d = a small-scale plant rating seen in the district — assumption |")
    L.append(row("Head grade, g/t", W2["grade"], lambda v: f"{v:g}") + " **assumption** |")
    L.append(row("Recovery", W2["recovery"], lambda v: f"{v:.0%}") + " gravity-only (Low) → gravity + leach (High; heavier permit stack) |")
    L.append(row("Margin retained by plant", W2["share"], lambda v: f"{v:.0%}") + " **placeholder** — own Minahang Bayan, integrated |")
    L.append(row("Plant operating cost, ₱/t", W2["opex_t"], lambda v: f"{v:,.0f}") + " assumption; rises with reagents |")
    L.append(row("Fixed overhead, ₱/month", W2["fixed"], php) + " assumption |")
    L.append(row("Plant build (capex)", W2["capex"], php) + " **assumption, no quotes** |")
    L.append(row("Permit stack", W2["permits"], php) + " assumption |")
    L.append("")
    L.append("| Result (per month) | Low | Base | High |")
    L.append("|---|---|---|---|")
    L.append(row("Ore treated, t", {k: r2[k]["t_m"] for k in K}, lambda v: f"{v:,.0f}"))
    L.append(row("Gold recovered, g", {k: r2[k]["au_g"] for k in K}, lambda v: f"{v:,.0f}"))
    L.append(row("Value of recovered gold at BSP", {k: r2[k]["value"] for k in K}, php))
    L.append(row("Plant gross (its retained margin)", {k: r2[k]["gross"] for k in K}, php))
    L.append(row("Plant net before tax", {k: r2[k]["net"] for k in K}, php))
    L.append(row(f"PGC's {PGC:.0%} of net after {CIT:.0%} tax (if declared)", {k: r2[k]["pgc"] for k in K}, php))
    pay = {k: (W2["capex"][k] + W2["permits"][k]) / r2[k]["net"] if r2[k]["net"] > 0 else float("inf") for k in K}
    L.append(row("Simple payback on capex + permits, months (pre-tax, from first steady-state month)", pay, lambda v: "n/a" if v == float("inf") else f"{v:,.0f}"))
    L.append("")
    L.append("Payback is pre-tax, measured from the first steady-state month, and ignores ramp-up, working capital and the build-and-permit lead time. The High column stacks the optimistic end of five independent assumptions at once — throughput, grade (no assays), recovery (needs the leach circuit and its permit stack), the plant's retained margin (a placeholder) and capex — so it is not a case, it is a ceiling. The Low column, which never pays back, is equally constructible.")
    L.append("")
    L.append("The Wave-2 spread is wide on purpose: it is driven by three unknowns we can actually resolve before committing capital — the ore test (recovery), the site and circuit decision (permit stack and opex), and a fabricator's quote (capex). Until those exist, the table says what the plant *could* be, not what it will be.")
    L.append("")
    # Wave 3
    L.append("### A3. Wave 3 — exploration earn-in on EXPA-000250-V (spend, not revenue)")
    L.append("")
    L.append("No production or resource figure is projected here: a resource is what the program is for, and only a Qualified Person may state one. What can be planned is the spend that earns PGC its majority of the project company, phased per the 36-month plan.")
    L.append("")
    L.append("| Program element | Low | Base | High | Status |")
    L.append("|---|---|---|---|---|")
    L.append(row("Phase 1 — baseline, access, shaft inventory, MOA, MB petition (months 1–6)", W3["phase1"], cad) + " assumption |")
    L.append(row("Phase 2 — underground mapping and sampling (months 7–18)", W3["phase2"], cad) + " assumption |")
    L.append(row("Phase 3 — diamond drilling, metres", W3["drill_m"], lambda v: f"{v:,.0f} m") + " assumption |")
    L.append(row("Drilling all-in cost, C$/m", W3["drill_cost"], lambda v: f"{v:,.0f}") + " assumption |")
    d = {k: W3["drill_m"][k] * W3["drill_cost"][k] for k in K}
    L.append(row("Phase 3 — drilling spend", d, cad))
    tot = {k: W3["phase1"][k] + W3["phase2"][k] + d[k] for k in K}
    L.append(row("**Exploration total over 36 months**", tot, cad))
    L.append(row("Listing costs (CPC/IPO, audit, QP report, exchange)", W3["listing"], cad) + " assumption |")
    L.append(row("**Total Canadian program, Wave 3**", {k: tot[k] + W3["listing"][k] for k in K}, cad))
    L.append("")
    L.append(f"For scale: the exchange's minimum recommended initial-phase program for a Tier 2 mining listing is C${TSXV_MIN_PHASE1:,.0f}, and the prior-expenditure test is waived where the non-contingent program exceeds C$400,000 — every case above clears both. What the spend buys is not a number in this annex: it is PGC's majority of the project company holding the permit, the NI 43-101 report that makes PGC listable, and the option on a 2,360-hectare district-scale property.")
    L.append("")
    # sensitivity
    L.append("### A4. What moves the numbers most")
    L.append("")
    L.append("| Lever | Effect on Wave 1 Base | Effect on Wave 2 Base | Who resolves it |")
    L.append("|---|---|---|---|")
    def base_with(W, **over):
        W2_ = {k: (dict(v) if isinstance(v, dict) else v) for k, v in W.items()}
        for kk, vv in over.items(): W2_[kk]["Base"] = vv
        return plant(W2_)["Base"]["net"]
    b1, b2 = r1["Base"]["net"], r2["Base"]["net"]
    def pct(new, old): return f"{(new/old-1):+.0%}" if old > 0 else "n/a"
    L.append(f"| Gold price −20% / +20% | {pct(b1 - 0.2*r1['Base']['gross'], b1)} / {pct(b1 + 0.2*r1['Base']['gross'], b1)} | {pct(b2 - 0.2*r2['Base']['gross'], b2)} / {pct(b2 + 0.2*r2['Base']['gross'], b2)} | the market |")
    L.append(f"| Recovery 50% instead of 60% / 70% (W2: 60% / 80% instead of 70%) | {pct(base_with(W1, recovery=0.50), b1)} / {pct(base_with(W1, recovery=0.70), b1)} | {pct(base_with(W2, recovery=0.60), b2)} / {pct(base_with(W2, recovery=0.80), b2)} | the ore test, then the circuit |")
    L.append(f"| Grade 2.5 g/t instead of 3.5 / 4.5 g/t | {pct(base_with(W1, grade=2.5), b1)} / {pct(base_with(W1, grade=4.5), b1)} | {pct(base_with(W2, grade=2.5), b2)} / {pct(base_with(W2, grade=4.5), b2)} | sampling and assays |")
    L.append(f"| Plant margin 25% instead of 35% / 45% (W2: 35% / 55% instead of 45%) | {pct(base_with(W1, share=0.25), b1)} / {pct(base_with(W1, share=0.45), b1)} | {pct(base_with(W2, share=0.35), b2)} / {pct(base_with(W2, share=0.55), b2)} | the ore-supply terms |")
    L.append("")
    L.append("*Annex generated by `opportunity_projections.py` from the inputs shown; regenerate after any input changes. Market inputs dated as stated.*")
    return "\n".join(L)

def main():
    s = open(MEMO, encoding="utf-8").read()
    block = "<!-- ANNEX-A-START -->\n" + annex() + "\n\n<!-- ANNEX-A-END -->"
    if "<!-- ANNEX-A-START -->" in s:
        s = re.sub(r"<!-- ANNEX-A-START -->.*?<!-- ANNEX-A-END -->", lambda m: block, s, flags=re.S)
    else:
        marker = "\n*Authorities relied on:"
        assert marker in s
        s = s.replace(marker, "\n---\n\n" + block + "\n\n" + marker, 1)
    open(MEMO, "w", encoding="utf-8").write(s)
    print(f"annex written; ₱/g = {PHP_PER_G:,.0f}")

if __name__ == "__main__":
    main()
