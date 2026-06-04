import json, psycopg2, psycopg2.extras
conn = psycopg2.connect('postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute('SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE', ('vSDQv1vfn6627bnA',))
nodes = cur.fetchone()['nodes']

# The sim-sender guard: if the original Telegram Trigger's sender starts with '999',
# substitute a sentinel chat_id ('0') that Telegram rejects with 400 → onError catches.
SIM_CHECK = "String($(\"Telegram Trigger\").first().json.message.from.id || \"\").startsWith(\"999\")"

# Every node that can send via Telegram. We force onError=continueRegularOutput so the
# exec keeps going to Log Leo Interaction, and we wrap chatId so it always lands on '0'
# for sim execs — Telegram will return 400 chat-not-found and the workflow proceeds.
TG_NODES = {
    'Ask Clarification', 'Reply to Jonathan', 'Reply to Client',
    'Send to Target Contact', 'Notify Jonathan of Resolution',
    'Confirm Context To Jonathan', 'Notify File Location',
    'Send Files Link to Recipient', 'Send Slash Help',
    'Send Onboarding Reply',
}

def wrap_expr(orig: str) -> str:
    # Strip the leading '=' if present, then rebuild as an n8n expression with the sim guard.
    inner = orig[2:-2].strip() if orig.startswith('={{') and orig.endswith('}}') else repr(orig)
    if not (orig.startswith('={{') and orig.endswith('}}')):
        # Literal value like '6513067717' — treat as a string literal in the ternary.
        inner = json.dumps(orig)
    return '={{ ' + SIM_CHECK + ' ? "0" : (' + inner + ') }}'

patched = []
for n in nodes:
    name = n.get('name')
    if name in TG_NODES:
        params = n.setdefault('parameters', {})
        original = params.get('chatId', '')
        if 'SIM' not in str(original) and 'startsWith' not in str(original):
            params['chatId'] = wrap_expr(original)
            n['onError'] = 'continueRegularOutput'
            n['continueOnFail'] = True
            patched.append(('chatId', name, original[:60]))
    elif name == 'Notify Jonathan Unauth':
        # HTTP node — patch the jsonBody to inject sim guard into chat_id.
        params = n.setdefault('parameters', {})
        body = params.get('jsonBody', '')
        if 'startsWith("999")' not in body and 'startsWith(\'999\')' not in body:
            # Replace 'chat_id: 6513067717,' with a sim-guarded ternary expression
            new_body = body.replace(
                'chat_id: 6513067717,',
                'chat_id: (' + SIM_CHECK.replace('\"','"') + ' ? 0 : 6513067717),'
            )
            if new_body != body:
                params['jsonBody'] = new_body
                n['onError'] = 'continueRegularOutput'
                n['continueOnFail'] = True
                patched.append(('jsonBody', name, '<chat_id replaced>'))

cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), 'vSDQv1vfn6627bnA'))
conn.commit()
for what, name, prev in patched:
    print(f'  {name}.{what}: was {prev!r} → sim-gated')
print(f'total patched: {len(patched)}')
