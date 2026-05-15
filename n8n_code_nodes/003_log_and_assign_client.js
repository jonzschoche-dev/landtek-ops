/**
 * n8n Code Node - Leo 1.0 (Recommended)
 * Place this RIGHT AFTER the Telegram Trigger node.
 */

const { execSync } = require('child_process');

const item = items[0].json;
const message = item.message || item;

const senderId = message.from?.id || message.chat?.id;
const senderName = message.from?.first_name || message.from?.username || "Unknown";
const text = message.text || message.caption || "";
const hasFile = !!(message.document || message.photo || message.video || message.audio);

const logData = {
    sender_id: senderId,
    sender_name: senderName,
    text: text,
    has_file: hasFile,
    workflow_node: "Telegram Trigger"
};

let client = null;

try {
    const result = execSync(`python3 /root/landtek/log_telegram_with_client.py`, {
        input: JSON.stringify(logData),
        encoding: 'utf-8'
    });

    const parsed = JSON.parse(result);
    client = parsed.client;
    console.log(`✅ Logged | Client: ${client}`);
} catch (error) {
    console.error("Logging error:", error.message);
}

item.sender_id = senderId;
item.sender_name = senderName;
item.has_file = hasFile;
item.client = client;
item.is_authorized = !!client;

return items;
