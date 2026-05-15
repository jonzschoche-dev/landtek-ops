/**
 * n8n Code Node - Context Builder for Leo 1.0
 * Place this node AFTER the client assignment node.
 * It fetches recent messages + open action items and prepares clean context for Leo.
 *
 * RUNTIME DEPENDENCY: /root/landtek/get_recent_context.py (deploy 013).
 * That helper currently has schema mismatches (column "sender_name" / "client"
 * don't exist on conversations / action_items). A follow-up deploy must fix
 * the helper's SQL before this Code node returns useful data.
 */

const { execSync } = require('child_process');

const item = items[0].json;
const client = item.client;

if (!client) {
    console.log("No client found. Skipping context building.");
    item.context = { recent_messages: [], open_action_items: [] };
    return items;
}

try {
    const result = execSync(`python3 /root/landtek/get_recent_context.py`, {
        input: JSON.stringify({ client: client }),
        encoding: 'utf-8'
    });

    const context = JSON.parse(result);

    item.context = context;
    console.log(`✅ Context built for client: ${client}`);

} catch (error) {
    console.error("Context Builder error:", error.message);
    item.context = { recent_messages: [], open_action_items: [] };
}

return items;
