#!/usr/bin/env python3
"""One-shot Gmail attachment puller for Civil Case 26-360 (and any has_attachments=true row).

Reads OAuth client from /root/landtek/gmail_oauth_client.json,
GMAIL_REFRESH_TOKEN from env. Refreshes access token, walks parts on
gmail.users.messages.get(format=full), downloads each non-inline attachment,
saves to OUT_DIR, updates gmail_messages.attachment_refs.
"""
import os, sys, json, base64, time, hashlib, psycopg2, urllib.request, urllib.parse
from psycopg2.extras import Json

PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'
OUT_DIR = '/root/landtek/case_files/MWK-001/civil_26-360_attachments'
CLIENT = json.load(open('/root/landtek/gmail_oauth_client.json'))['web']
REFRESH = os.environ.get('GMAIL_REFRESH_TOKEN')
if not REFRESH: sys.exit("GMAIL_REFRESH_TOKEN not set")

def refresh_access_token():
    data = urllib.parse.urlencode({
        'client_id': CLIENT['client_id'],
        'client_secret': CLIENT['client_secret'],
        'refresh_token': REFRESH,
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request(CLIENT['token_uri'], data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    return body['access_token']

def gmail_get(path, token, params=None):
    url = f'https://gmail.googleapis.com/gmail/v1/users/me{path}'
    if params: url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def walk_parts(part, out):
    """Recursively collect parts that look like attachments (have filename + body.attachmentId)."""
    fn = part.get('filename') or ''
    body = part.get('body') or {}
    if fn and body.get('attachmentId'):
        mime = part.get('mimeType') or ''
        # Inline images sometimes have filenames; check Content-Disposition if present
        disposition = ''
        for h in (part.get('headers') or []):
            if h.get('name','').lower() == 'content-disposition':
                disposition = h.get('value','')
        out.append({
            'filename': fn,
            'mime_type': mime,
            'attachment_id': body['attachmentId'],
            'size_bytes': body.get('size'),
            'content_disposition': disposition,
        })
    for sub in (part.get('parts') or []):
        walk_parts(sub, out)

def safe_filename(message_id, fn):
    base = os.path.basename(fn).strip().replace('/', '_')[:120]
    if not base: base = 'unnamed.bin'
    return f'{message_id[:16]}__{base}'

def main():
    token = refresh_access_token()
    print(f'token ok, len={len(token)}')

    conn = psycopg2.connect(PG)
    cur = conn.cursor()
    cur.execute("""SELECT id, message_id, subject
                     FROM gmail_messages
                    WHERE has_attachments=true
                      AND (attachment_refs IS NULL OR jsonb_array_length(attachment_refs)=0)
                    ORDER BY id""")
    rows = cur.fetchall()
    print(f'{len(rows)} messages need attachment fetch')

    total_pulled, total_skipped, total_failed = 0, 0, 0
    for db_id, msg_id, subj in rows:
        try:
            msg = gmail_get(f'/messages/{msg_id}', token, {'format': 'full'})
            atts = []
            walk_parts(msg.get('payload') or {}, atts)
            if not atts:
                # has_attachments was true but no actual attachment parts — note empty array
                cur.execute("UPDATE gmail_messages SET attachment_refs=%s WHERE id=%s",
                            (Json([]), db_id))
                conn.commit()
                print(f'  msg {db_id}: no attachment parts (was flagged)')
                total_skipped += 1
                continue
            refs = []
            for a in atts:
                payload = gmail_get(f'/messages/{msg_id}/attachments/{a["attachment_id"]}', token)
                raw = base64.urlsafe_b64decode(payload['data'] + '=' * (-len(payload['data']) % 4))
                sha = hashlib.sha256(raw).hexdigest()[:16]
                local_name = safe_filename(msg_id, a['filename'])
                local_path = os.path.join(OUT_DIR, local_name)
                with open(local_path, 'wb') as f: f.write(raw)
                refs.append({
                    'filename': a['filename'],
                    'mime_type': a['mime_type'],
                    'size_bytes': len(raw),
                    'attachment_id': a['attachment_id'],
                    'local_path': local_path,
                    'sha256_16': sha,
                    'inline': 'inline' in (a['content_disposition'] or '').lower(),
                })
            cur.execute("UPDATE gmail_messages SET attachment_refs=%s WHERE id=%s",
                        (Json(refs), db_id))
            conn.commit()
            print(f'  msg {db_id}: pulled {len(refs)} ({", ".join(r["filename"] for r in refs)[:120]})')
            total_pulled += len(refs)
            time.sleep(0.25)  # polite throttle
        except Exception as e:
            print(f'  msg {db_id}: FAILED — {str(e)[:200]}')
            total_failed += 1

    print(f'\nDONE: pulled={total_pulled}, msgs_empty={total_skipped}, failed_msgs={total_failed}')

if __name__ == '__main__':
    main()
