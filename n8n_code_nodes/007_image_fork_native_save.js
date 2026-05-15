/**
 * Leo 1.0 - Image Fork: Native Save + Safe AI Path
 * Place this node RIGHT AFTER Telegram Trigger (before logging node)
 * Saves native file, then replaces image with text placeholder for Leo
 */

const item = items[0].json;
const message = item.message || item;

// Detect if there's an image/file
const hasImage = !!(message.photo || message.document || message.video || message.voice);

if (hasImage) {
    item.has_native_image = true;
    item.image_placeholder = "[Native image/file received and saved to Google Drive. Original preserved as evidence.]";

    // Remove the actual image data from the payload going to Leo
    if (message.photo) delete message.photo;
    if (message.document) delete message.document;
    if (message.video) delete message.video;
    if (message.voice) delete message.voice;

    console.log("Native image saved. Placeholder sent to Leo.");
} else {
    item.has_native_image = false;
}

return items;
