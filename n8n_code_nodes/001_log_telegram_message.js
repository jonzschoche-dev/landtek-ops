/**
 * n8n Code Node - Log every incoming Telegram message
 * Place this as one of the first nodes after the Telegram Trigger.
 *
 * This calls the Python logging function we created for Leo 1.0.
 *
 * NOTE: as written below, this calls `python3 /root/landtek/log_telegram_event.py`
 * and pipes JSON via stdin. The current log_telegram_event.py (deploy 003) does
 * NOT yet read stdin and call the function — it only prints a readiness string
 * when run as __main__. A follow-up deploy needs to either:
 *   (a) update log_telegram_event.py to read JSON from stdin and call
 *       log_telegram_event(json.loads(sys.stdin.read())); or
 *   (b) change this snippet to: execSync(`python3 -c "import sys, json; \
 *       sys.path.insert(0,'/root/landtek'); from log_telegram_event import \
 *       log_telegram_event; log_telegram_event(json.loads(sys.argv[1]))" '${JSON.stringify(logData)}'`)
 */

const { execSync } = require('child_process');

// Get data from the Telegram trigger
const telegramData = items[0].json;
const message = telegramData.message || telegramData;

const senderId = message.from?.id;
const senderName = message.from?.first_name || message.from?.username || "Unknown";
const text = message.text || "";
const hasFile = !!(message.document || message.photo || message.video);

// Prepare data for logging
const logData = {
    sender_id: senderId,
    sender_name: senderName,
    text: text,
    has_file: hasFile,
    attempted_case_file: null,           // We will improve this later
    workflow_node: "Telegram Trigger"
};

// Call the Python logging function
try {
    const result = execSync(
        `python3 /root/landtek/log_telegram_event.py`,
        {
            input: JSON.stringify(logData),
            encoding: 'utf-8'
        }
    );
    console.log("Logged to telegram_activity.log");
} catch (error) {
    console.error("Logging failed:", error.message);
}

// Pass data forward
return items;
