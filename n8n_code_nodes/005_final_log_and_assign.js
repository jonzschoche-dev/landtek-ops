/**
 * Leo 1.0 - Log + Client Assignment (Final)
 * Place this node RIGHT AFTER the Telegram Trigger.
 */

const { execSync } = require('child_process');

const item = items[0].json;
const message = item.message || item;

const senderId = message.from?.id || message.chat?.id;
const senderName = message.from?.first_name || message.from?.username || "Unknown";
const text = message.text || message.caption || "";
const hasFile = !!(message.document || message.photo || message.video || message.audio || message.voice);

// === CLIENT MAPPING ===
const CLIENT_MAP = {
    8575986732: "mwk",      // Don Qi Style
    6513067717: "owner"     // Jonathan Zschoche
};

const client = CLIENT_MAP[senderId] || null;
const isAuthorized = !!client;

const logData = {
    sender_id: senderId,
    sender_name: senderName,
    text: text,
    has_file: hasFile,
    client: client,
    workflow_node: "Telegram Trigger"
};

try {
    execSync(`python3 /root/landtek/log_telegram_with_client.py`, {
        input: JSON.stringify(logData),
        encoding: 'utf-8'
    });
} catch (e) {
    console.error("Logging failed:", e.message);
}

item.sender_id = senderId;
item.sender_name = senderName;
item.client = client;
item.is_authorized = isAuthorized;
item.has_file = hasFile;

return items;
