"""Build the Postgres DSN without a password in source (Phase 0, 24 Oct 2026).
Order: PG_DSN env; else PGUSER/PGPASSWORD from env or ~/.landtek_db.env (600 file)."""
import os

def _envfile():
    out = {}
    for p in (os.path.expanduser("~/.landtek_db.env"), "/root/.landtek_db.env"):
        try:
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.replace("export ", "").strip()] = v.strip().strip("'\"")
            break
        except OSError:
            continue
    return out

def dsn(hostport):
    if os.environ.get("PG_DSN"):
        return os.environ["PG_DSN"]
    f = _envfile()
    user = os.environ.get("PGUSER") or f.get("PGUSER", "n8n")
    pw = os.environ.get("PGPASSWORD") or f.get("PGPASSWORD", "")
    return f"postgresql://{user}:{pw}@{hostport}/n8n"
