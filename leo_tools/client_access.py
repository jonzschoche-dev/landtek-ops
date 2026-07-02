"""LandTek client access — the EXTERNAL, token-gated client entry surface.

This is the trust boundary of the product. A retainer client is handed one
opaque magic-link:

    https://leo.hayuma.org/client/<token>

and reaches ONLY their own portal — never the /ops cockpit, never another
client's portal, never /files/ (ops-gated). The design that makes that true:

  * The route lives under /client/<token> in its OWN blueprint (url_prefix
    "/client"). nginx proxies /client/ WITHOUT basic-auth (a client cannot have
    the ops password) but this module enforces its own token check. The /ops/
    location keeps its auth_basic gate untouched — so a token holder physically
    cannot reach /ops/* (nginx would demand the ops password the client lacks).

  * There is NO client_code in the URL. The token resolves, server-side, to
    exactly one client_code from client_access_tokens. A holder therefore has
    no lever to pivot to another client (contrast /ops/portal/<code>, which is
    for Jonathan and stays behind the ops gate).

  * Tokens are stored HASHED (sha256). The plaintext is emitted once at mint
    time and never persisted. Lookup hashes the presented token and compares in
    constant time. Unknown / revoked / malformed → 404 (we do not distinguish,
    so the surface leaks nothing about which tokens exist).

Mint / revoke from the shell:

    python3 client_access.py mint  MWK-001      --label "handed 2026-07-02"
    python3 client_access.py mint  Paracale-001 --label "handed 2026-07-02"
    python3 client_access.py list
    python3 client_access.py revoke <token_id>

Reuses render_client_portal() from client_portal.py (one portal, one truth) and
wraps it in the client-only chrome (_client_layout — no ops nav).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sys

import psycopg2
from flask import Blueprint, abort

from ops_dashboard import PG_DSN

bp = Blueprint("client_access", __name__, url_prefix="/client")


@bp.after_request
def _no_referrer(resp):
    """LOW-1: never leak the magic-link token via the Referer header on outbound
    links / embedded assets. Applies to every response this blueprint emits (portal
    HTML, streamed docs, matter tables)."""
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# Opaque token: URL-safe, ~43 chars from 32 bytes of entropy. Only hex-token
# shapes are accepted at the route to reject obviously-garbage input cheaply.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,120}$")


def _db():
    return psycopg2.connect(PG_DSN)


def _hash_token(token: str) -> str:
    """sha256 hex of the token. We store/compare only this, never plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _resolve_token(token: str) -> str | None:
    """Return the client_code for a LIVE token, else None.

    Constant-time comparison against every live hash so a timing side-channel
    cannot distinguish 'no such token' from 'revoked'. Also stamps last_seen_at
    on a hit (best-effort audit — failure to stamp never blocks access)."""
    if not token or not _TOKEN_RE.match(token):
        return None
    presented = _hash_token(token)
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, token_hash, client_code FROM client_access_tokens "
            "WHERE revoked_at IS NULL"
        )
        match_id = None
        match_client = None
        for row_id, thash, client_code in cur.fetchall():
            # constant-time compare; keep scanning even after a match so total
            # work does not depend on match position.
            if hmac.compare_digest(thash, presented):
                match_id = row_id
                match_client = client_code
        if match_id is not None:
            try:
                cur.execute(
                    "UPDATE client_access_tokens SET last_seen_at = now() WHERE id = %s",
                    (match_id,),
                )
            except Exception:
                pass
        return match_client
    finally:
        cur.close()
        conn.close()


# ─────────────────────────── ownership checks ────────────────────────────────
# The trust boundary: a token holder may reach ONLY documents/matters that belong
# to their client_code. Every doc/matter fetch under /client/<token>/… passes one
# of these BEFORE any bytes are streamed. Parameterized SQL only; no client-supplied
# value ever selects another client's scope.


def _client_owns_matter(client_code: str, matter_code: str) -> bool:
    """True iff matter_code is one of THIS client's matters (matters.client_code —
    the NOT-NULL validated FK, never free-text case_file)."""
    if not client_code or not matter_code:
        return False
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM matters WHERE matter_code = %s AND client_code = %s",
            (matter_code, client_code),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def _client_owns_doc(client_code: str, doc_id: int) -> bool:
    """True iff document `doc_id` belongs to THIS client. A doc belongs to a client
    when ANY of these hold, all scoped by the VALIDATED client tag:
      * its case_file equals this client's validated (non-empty) case_file, OR
      * its matter_code is one of this client's matters, OR
      * it is linked (document_matter_links) to one of this client's matters.
    The client's case_file is required non-empty (guard `cf.case_file <> ''`) so a
    blank-case_file doc can never match a client whose case_file is blank."""
    if not client_code:
        return False
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
              FROM documents d
             WHERE d.id = %s
               AND (
                     -- (a) same validated, non-empty case_file
                     EXISTS (SELECT 1 FROM clients c
                              WHERE c.client_code = %s
                                AND COALESCE(c.case_file,'') <> ''
                                AND c.case_file = d.case_file)
                     -- (b) doc's own matter_code belongs to this client
                  OR (d.matter_code IS NOT NULL AND EXISTS (
                        SELECT 1 FROM matters m
                         WHERE m.matter_code = d.matter_code
                           AND m.client_code = %s))
                     -- (c) doc linked to one of this client's matters
                  OR EXISTS (SELECT 1
                               FROM document_matter_links l
                               JOIN matters m ON m.matter_code = l.matter_code
                              WHERE l.doc_id = d.id
                                AND m.client_code = %s)
                   )
            """,
            (doc_id, client_code, client_code, client_code),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def _token_link_builder(token: str):
    """Return (doc_url_fn, matter_url_fn) that emit TOKEN-SCOPED, ownership-checked
    URLs for the client chrome. render_client_portal routes every doc/matter link
    through these so NO bare /files/c/ string ever reaches client HTML (CRITICAL-1).
    The token is already URL-safe (validated by _TOKEN_RE) so no escaping is needed;
    matter_code is url-quoted defensively for the path segment."""
    from urllib.parse import quote

    def doc_url(doc_id: int) -> str:
        return f"/client/{token}/doc/{int(doc_id)}"

    def matter_url(matter_code: str) -> str:
        return f"/client/{token}/m/{quote(str(matter_code), safe='')}"

    return doc_url, matter_url


@bp.route("/<token>")
def client_entry(token: str):
    """The client's own portal, reached by their magic-link token ONLY.

    Unknown / revoked / malformed token → 404 (no information leak). A valid
    token renders exactly one client's portal in the client-only chrome, with
    every doc/matter link rewritten to the token-scoped, ownership-checked routes."""
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    # Import lazily to avoid a hard import cycle at module load.
    from client_portal import _client_layout, render_client_portal
    title, body = render_client_portal(client_code, link_builder=_token_link_builder(token))
    return _client_layout(title, body)


@bp.route("/<token>/doc/<int:doc_id>")
def client_doc(token: str, doc_id: int):
    """Stream a single document to the token holder — ONLY if that doc belongs to
    the token's client. Unknown/revoked/malformed token → 404; a doc the client does
    not own → 404 (indistinguishable, no leak of what exists). On pass, delegate to
    the existing files_public.serve logic (disk → Drive fallback)."""
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    if not _client_owns_doc(client_code, doc_id):
        abort(404)
    from files_public import serve as _serve
    return _serve(doc_id)


@bp.route("/<token>/m/<matter_code>")
def client_matter(token: str, matter_code: str):
    """Render the per-matter document list for the token holder — ONLY if that matter
    belongs to the token's client. Token/ownership mismatch → 404. On pass, delegate
    to the existing files_public.matter_table renderer (which itself only lists that
    one matter's docs). The doc links inside it are then re-pointed through the
    token-scoped doc route by post-processing the HTML so a client can't be handed a
    bare /files/c/ link from the reused renderer."""
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    if not _client_owns_matter(client_code, matter_code):
        abort(404)
    from files_public import matter_table as _matter_table
    resp = _matter_table(matter_code)
    # Re-point every /files/c/<id> href in the reused renderer's HTML to the
    # token-scoped, ownership-checked doc route. Keeps CRITICAL-1 intact: no bare
    # /files/c/ reaches the client. Only the numeric-id doc links appear here.
    try:
        html_body = resp.get_data(as_text=True)
        doc_url, _ = _token_link_builder(token)
        html_body = re.sub(
            r'/files/c/(\d+)',
            lambda mo: doc_url(int(mo.group(1))),
            html_body,
        )
        resp.set_data(html_body)
    except Exception:
        # If anything about the reused response is unexpected, fail closed: do not
        # emit a body that might contain a bare /files/c link.
        abort(404)
    return resp


# ─────────────────────────── mint / revoke CLI ───────────────────────────────

def mint_token(client_code: str, label: str | None = None) -> str:
    """Create a token for a client, store its hash, return the PLAINTEXT once.

    Validates that the client_code exists (FK would catch it too, but a clear
    error beats a constraint traceback). The returned string is the only time
    the plaintext is available."""
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM clients WHERE client_code = %s", (client_code,))
        if not cur.fetchone():
            raise SystemExit(f"error: no client with client_code={client_code!r}")
        token = secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO client_access_tokens (token_hash, client_code, label) "
            "VALUES (%s, %s, %s) RETURNING id",
            (_hash_token(token), client_code, label),
        )
        tid = cur.fetchone()[0]
        return token, tid
    finally:
        cur.close()
        conn.close()


def revoke_token(token_id: int) -> bool:
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE client_access_tokens SET revoked_at = now() "
            "WHERE id = %s AND revoked_at IS NULL RETURNING id",
            (token_id,),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def list_tokens():
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, client_code, label, created_at, revoked_at, last_seen_at "
            "FROM client_access_tokens ORDER BY id"
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _base_url() -> str:
    return os.getenv("LANDTEK_PUBLIC_BASE", "https://leo.hayuma.org")


def _cli():
    args = sys.argv[1:]
    if not args:
        print(__doc__.split("Mint / revoke")[1].strip() if "Mint" in __doc__ else "")
        print("commands: mint <client_code> [--label TEXT] | revoke <id> | list")
        return
    cmd = args[0]
    if cmd == "mint":
        if len(args) < 2:
            raise SystemExit("usage: mint <client_code> [--label TEXT]")
        client_code = args[1]
        label = None
        if "--label" in args:
            i = args.index("--label")
            label = args[i + 1] if i + 1 < len(args) else None
        token, tid = mint_token(client_code, label)
        print(f"minted token id={tid} for {client_code}")
        print(f"  link: {_base_url()}/client/{token}")
        print("  (plaintext shown once — copy it now; only the hash is stored)")
    elif cmd == "revoke":
        if len(args) < 2:
            raise SystemExit("usage: revoke <token_id>")
        ok = revoke_token(int(args[1]))
        print("revoked" if ok else "no live token with that id (already revoked?)")
    elif cmd == "list":
        rows = list_tokens()
        if not rows:
            print("(no tokens)")
            return
        for tid, cc, label, created, revoked, seen in rows:
            state = "REVOKED" if revoked else "live"
            print(f"  id={tid}  {cc:14}  {state:8}  {label or ''}  "
                  f"created={created}  last_seen={seen or '—'}")
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    _cli()
