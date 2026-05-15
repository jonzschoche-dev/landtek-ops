/**
 * Leo 1.0 - Output Parser + Saver
 * Place this node AFTER Parse Agent1 (or after the AI Agent if Parse Agent1 is not used).
 * It takes Leo's structured output and saves action items, calendar events, and notes.
 */

const { execSync } = require('child_process');

const item = items[0].json;

// Get the data we need
const client = item.client || item.case_file;
const leoOutput = item.leo_output || item; // fallback if structure is flat

if (!client) {
    console.log("No client found. Skipping output parsing.");
    return items;
}

const payload = {
    client: client,
    leo_output: leoOutput
};

try {
    const result = execSync(`python3 /root/landtek/parse_leo_output.py`, {
        input: JSON.stringify(payload),
        encoding: 'utf-8'
    });

    const parsed = JSON.parse(result);
    console.log("Output parsed and saved:", parsed.processed);

    item.output_saved = parsed;

} catch (error) {
    console.error("Output parsing failed:", error.message);
    item.output_saved = { status: "error", message: error.message };
}

return items;
