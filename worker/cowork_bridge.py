#!/usr/bin/env python3
"""Cowork-Drive Bridge daemon.

Polls Drive Cowork-Commands folder for command files written by Cowork,
executes them on the VPS, and writes outputs to Cowork-Outputs folder.

Command file schema (JSON):
{
  "id": "uuid-or-string",
  "type": "shell | python | psql | file_write | file_read | n8n_api",
  "payload": { type-specific },
  "timeout_s": 120
}

Output file schema (JSON):
{
  "id": "<same id>",
  "type": "...", "executed_at": "ISO",
  "exit_code": 0, "stdout": "...", "stderr": "...",
  "duration_s": 1.2, "error": null
}
"""
import os, sys, json, time, subprocess, traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import GOOGLE_CREDS, PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD

CMDS_FOLDER = os.getenv("COWORK_CMDS_FOLDER", "1ytcq-kikbqfGOK0cdslhdqqpQqTmAiRg")
OUTPUTS_FOLDER = os.getenv("COWORK_OUTPUTS_FOLDER", "1U6XwjD7UI4NHiWAKKKEbu-JDzjnjI9EW")
POLL_INTERVAL_S = int(os.getenv("COWORK_POLL_INTERVAL_S", "30"))
SEEN_FILE = Path("/var/lib/landtek/cowork_seen.json")
DEFAULT_TIMEOUT = 120
MAX_OUTPUT_BYTES = 100_000


def log(m): print(f"[{datetime.now().isoformat()}] {m}", flush=True)


def get_drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def load_seen():
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SEEN_FILE.exists(): return set()
    try: return set(json.loads(SEEN_FILE.read_text()))
    except Exception: return set()


def save_seen(seen):
    keep = sorted(seen)[-2000:]
    SEEN_FILE.write_text(json.dumps(list(keep)))


def list_cmds(service):
    resp = service.files().list(
        q=f"'{CMDS_FOLDER}' in parents and trashed=false and mimeType='application/json'",
        fields="files(id,name,modifiedTime,size,createdTime)",
        pageSize=100, orderBy="createdTime",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    return resp.get("files", [])


def download_cmd(service, file_id):
    data = service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    return json.loads(data)


def upload_output(service, cmd_id, output):
    from googleapiclient.http import MediaInMemoryUpload
    body = json.dumps(output, default=str, indent=2)
    name = f"out_{cmd_id}.json"
    media = MediaInMemoryUpload(body.encode("utf-8"), mimetype="application/json")
    service.files().create(
        body={"name": name, "parents": [OUTPUTS_FOLDER]},
        media_body=media, supportsAllDrives=True,
    ).execute()


def truncate(s, n=MAX_OUTPUT_BYTES):
    if not s: return s
    return s if len(s) <= n else s[:n] + f"\n[...truncated {len(s)-n} bytes]"


# ---------- executors ---------------------------------------------------------
def exec_shell(payload, timeout):
    cmd = payload.get("command", "")
    try:
        r = subprocess.run(["bash","-lc",cmd], capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": truncate(r.stdout), "stderr": truncate(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "error": f"timeout after {timeout}s"}


def exec_python(payload, timeout):
    code = payload.get("code", "")
    try:
        r = subprocess.run(["python3","-c",code], capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": truncate(r.stdout), "stderr": truncate(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "error": f"timeout after {timeout}s"}


def exec_psql(payload, timeout):
    sql = payload.get("sql", "")
    db = payload.get("db", "n8n"); user = payload.get("user", "n8n")
    cmd = ["docker","exec","-i","n8n-postgres-1","psql","-U",user,"-d",db,"-c", sql]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": truncate(r.stdout), "stderr": truncate(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "error": f"timeout after {timeout}s"}


def exec_file_write(payload, timeout):
    path = payload.get("path"); content = payload.get("content", "")
    encoding = payload.get("encoding", "text")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if encoding == "base64":
            import base64
            Path(path).write_bytes(base64.b64decode(content))
            return {"exit_code": 0, "stdout": f"wrote {len(content)*3//4} bytes (base64) to {path}"}
        else:
            Path(path).write_text(content)
            return {"exit_code": 0, "stdout": f"wrote {len(content)} chars to {path}"}
    except Exception as e:
        return {"exit_code": -1, "error": str(e)}


def exec_file_read(payload, timeout):
    path = payload.get("path"); max_bytes = int(payload.get("max_bytes", MAX_OUTPUT_BYTES))
    try:
        text = Path(path).read_text(errors="replace")
        return {"exit_code": 0, "stdout": truncate(text, max_bytes)}
    except Exception as e:
        return {"exit_code": -1, "error": str(e)}


def exec_n8n_api(payload, timeout):
    method = payload.get("method", "GET").upper()
    path = payload.get("path", "")
    body = payload.get("body")
    env_text = Path("/root/landtek/.env").read_text()
    api_key = ""
    for line in env_text.splitlines():
        if line.startswith("N8N_API_KEY="):
            api_key = line.split("=", 1)[1].strip()
            break
    url = f"http://localhost:5678/api/v1{path}"
    cmd = ["curl","-s","-w","\nHTTP_STATUS:%{http_code}","-X",method,
           "-H",f"X-N8N-API-KEY: {api_key}", "-H","Content-Type: application/json"]
    if body is not None:
        bs = body if isinstance(body, str) else json.dumps(body)
        cmd += ["-d", bs]
    cmd += [url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": truncate(r.stdout), "stderr": truncate(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "error": f"timeout after {timeout}s"}


EXECUTORS = {
    "shell": exec_shell, "python": exec_python, "psql": exec_psql,
    "file_write": exec_file_write, "file_read": exec_file_read,
    "n8n_api": exec_n8n_api,
}


def audit_pg(action, target_id, summary):
    try:
        import psycopg2
        conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DATABASE,
                                user=PG_USER, password=PG_PASSWORD)
        cur = conn.cursor()
        cur.execute("""INSERT INTO audit_log
            (actor, actor_type, action, target_type, target_id, after_state)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
            ("cowork_bridge", "worker", action, "cowork_command", str(target_id),
             json.dumps(summary, default=str)[:5000]))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log(f"  audit insert failed: {e}")


def process_cmd(service, cmd_file):
    file_id = cmd_file["id"]; name = cmd_file["name"]
    log(f"  processing {name} ({file_id})")
    try:
        cmd = download_cmd(service, file_id)
    except Exception as e:
        upload_output(service, file_id, {
            "id": file_id, "error": f"download_failed: {e}",
            "executed_at": datetime.now(timezone.utc).isoformat()})
        return
    cmd_id = cmd.get("id", file_id)
    cmd_type = cmd.get("type", "shell")
    payload = cmd.get("payload", {})
    timeout = int(cmd.get("timeout_s", DEFAULT_TIMEOUT))

    executor = EXECUTORS.get(cmd_type)
    if not executor:
        result = {"exit_code": -1, "error": f"unknown command type: {cmd_type}"}
    else:
        t0 = time.time()
        try:
            result = executor(payload, timeout)
        except Exception as e:
            result = {"exit_code": -1, "error": f"executor_crash: {e}",
                      "traceback": traceback.format_exc()}
        result["duration_s"] = round(time.time() - t0, 3)

    output = {"id": cmd_id, "command_file_id": file_id, "command_name": name,
              "type": cmd_type, "executed_at": datetime.now(timezone.utc).isoformat(),
              **result}
    try:
        upload_output(service, cmd_id, output)
        log(f"  ✓ uploaded out_{cmd_id}.json (exit={result.get('exit_code')}, dur={result.get('duration_s')}s)")
        audit_pg("cowork_exec", cmd_id,
                 {"type": cmd_type, "exit_code": result.get("exit_code"),
                  "duration_s": result.get("duration_s")})
    except Exception as e:
        log(f"  ✗ upload failed: {e}")


def main():
    log(f"cowork_bridge starting (poll={POLL_INTERVAL_S}s)")
    log(f"  cmds={CMDS_FOLDER}  outputs={OUTPUTS_FOLDER}")
    seen = load_seen()
    log(f"  loaded {len(seen)} previously-seen ids")
    service = get_drive_service()
    while True:
        try:
            files = list_cmds(service)
            new = [f for f in files if f["id"] not in seen]
            if new:
                log(f"  found {len(new)} new command(s)")
            for f in new:
                process_cmd(service, f)
                seen.add(f["id"])
            if new:
                save_seen(seen)
        except Exception as e:
            log(f"poll error: {e}")
            traceback.print_exc()
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
