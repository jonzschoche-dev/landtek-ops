/**
 * n8n Code Node - Log every incoming Telegram message for Leo 1.0
 * Place this node RIGHT AFTER the Telegram Trigger node.
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
    attempted_case_file: null,   // We will improve this in next deploy
    workflow_node: "Telegram Trigger"
};

try {
    const result = execSync(`python3 /root/landtek/log_telegram_event.py`, {
        input: JSON.stringify(logData),
        encoding: 'utf-8'
    });
    console.log("✅ Telegram message logged successfully");
} catch (error) {
    console.error("❌ Logging failed:", error.message);
}

return items;
