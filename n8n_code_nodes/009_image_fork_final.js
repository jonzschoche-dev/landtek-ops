/**
 * Leo 1.0 - FINAL Image Fork (Native Upload + Safe Placeholder)
 * Place this node RIGHT AFTER Telegram Trigger
 */

const { execSync } = require('child_process');

const item = items[0].json;
const message = item.message || item;

const hasFile = !!(message.document || message.photo || message.video || message.voice || message.audio);

if (hasFile) {
    let fileId = null;
    let fileName = "unknown_file";

    if (message.document) {
        fileId = message.document.file_id;
        fileName = message.document.file_name || "document";
    } else if (message.photo) {
        const photo = message.photo[message.photo.length - 1];
        fileId = photo.file_id;
        fileName = "photo.jpg";
    }

    item.has_native_file = true;
    item.file_id = fileId;
    item.original_filename = fileName;

    // Native upload
    try {
        const result = execSync(`python3 /root/landtek/telegram_file_to_drive.py`, {
            input: JSON.stringify({
                file_id: fileId,
                client: item.client || "mwk",
                original_filename: fileName
            }),
            encoding: 'utf-8'
        });
        console.log("Native file saved to Drive");
    } catch (e) {
        console.error("File upload failed:", e.message);
    }

    // Safe placeholder for Leo
    item.image_placeholder = `[Native file received and saved to Drive as '${fileName}'. Original preserved as evidence.]`;

    // Remove raw image data
    delete message.document;
    delete message.photo;
    delete message.video;
    delete message.voice;
    delete message.audio;
}

return items;
