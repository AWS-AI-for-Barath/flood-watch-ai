/**
 * processFloodAI — Phase 2 Lambda
 * 
 * Triggered by S3 ObjectCreated on media/* prefix.
 * Extracts frames from uploaded media, invokes Bedrock Nova Lite,
 * and writes strict 4-key analysis JSON to s3://floodwatch-uploads/analysis/<uuid>.json
 * 
 * Runtime: Node.js 20 | Memory: 512MB | Timeout: 30s
 */

import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
import { execSync } from "child_process";
import { writeFileSync, readFileSync, mkdirSync, unlinkSync, readdirSync } from "fs";
import { join } from "path";

const s3 = new S3Client({});
const bedrock = new BedrockRuntimeClient({ region: process.env.AWS_REGION || "us-east-1" });

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const MODEL_ID = "amazon.nova-lite-v1:0";
const MAX_FRAMES = 3;

// Exact prompt from spec (< 150 tokens)
const ANALYSIS_PROMPT = `Analyze this flood image and respond strictly in JSON:
{
  "people_trapped": boolean,
  "infrastructure_damage": boolean,
  "severity": "low" or "medium" or "high",
  "submergence_ratio": float between 0 and 1
}`;

// ================================================================
//  FRAME EXTRACTION
// ================================================================

/**
 * Download media from S3 and extract up to MAX_FRAMES key frames.
 * Returns array of { base64, format } objects.
 */
async function frameExtraction(bucket, key) {
    console.log(`[FrameExtraction] Downloading s3://${bucket}/${key}`);

    // Download from S3 to /tmp
    const getCmd = new GetObjectCommand({ Bucket: bucket, Key: key });
    const response = await s3.send(getCmd);
    const chunks = [];
    for await (const chunk of response.Body) {
        chunks.push(chunk);
    }
    const buffer = Buffer.concat(chunks);

    const ext = key.split(".").pop().toLowerCase();
    const localPath = `/tmp/input.${ext}`;
    writeFileSync(localPath, buffer);
    console.log(`[FrameExtraction] Saved ${buffer.length} bytes to ${localPath}`);

    const imageExts = ["jpg", "jpeg", "png", "bmp"];
    const videoExts = ["mp4", "mov", "avi", "webm"];

    if (imageExts.includes(ext)) {
        // Single image — return directly as one frame
        const base64 = buffer.toString("base64");
        const format = ext === "png" ? "png" : "jpeg";
        console.log(`[FrameExtraction] Image mode: 1 frame extracted`);
        return [{ base64, format }];
    }

    if (videoExts.includes(ext)) {
        return extractVideoFrames(localPath);
    }

    throw new Error(`Unsupported media format: .${ext}`);
}

/**
 * Extract 2-3 key frames from a video using ffmpeg.
 * Uses the ffmpeg binary available in Lambda Layer or bundled.
 */
function extractVideoFrames(videoPath) {
    const outDir = "/tmp/frames";
    mkdirSync(outDir, { recursive: true });

    // Clean any previous frames
    try {
        readdirSync(outDir).forEach(f => unlinkSync(join(outDir, f)));
    } catch (_) { /* empty */ }

    // Probe video duration
    let duration = 10; // default fallback
    try {
        const probeResult = execSync(
            `ffprobe -v error -show_entries format=duration -of csv=p=0 "${videoPath}"`,
            { encoding: "utf-8", timeout: 5000 }
        ).trim();
        duration = parseFloat(probeResult) || 10;
    } catch (e) {
        console.warn("[FrameExtraction] ffprobe failed, using default duration:", e.message);
    }

    // Calculate timestamps for 2-3 frames (start, middle, ~80%)
    const timestamps = [];
    if (duration <= 2) {
        timestamps.push(0); // Very short video: 1 frame
    } else if (duration <= 5) {
        timestamps.push(0, duration / 2); // Short: 2 frames
    } else {
        timestamps.push(0, duration / 2, duration * 0.8); // Normal: 3 frames
    }

    console.log(`[FrameExtraction] Video duration: ${duration.toFixed(1)}s — extracting ${timestamps.length} frames`);

    // Extract frames using ffmpeg
    const frames = [];
    for (let i = 0; i < timestamps.length && i < MAX_FRAMES; i++) {
        const outPath = join(outDir, `frame_${i}.jpg`);
        try {
            execSync(
                `ffmpeg -y -ss ${timestamps[i].toFixed(2)} -i "${videoPath}" -frames:v 1 -q:v 2 "${outPath}"`,
                { timeout: 8000, stdio: "pipe" }
            );
            const frameBuffer = readFileSync(outPath);
            frames.push({
                base64: frameBuffer.toString("base64"),
                format: "jpeg"
            });
            console.log(`[FrameExtraction] Frame ${i} extracted (${frameBuffer.length} bytes)`);
        } catch (e) {
            console.warn(`[FrameExtraction] Failed to extract frame ${i}:`, e.message);
        }
    }

    if (frames.length === 0) {
        throw new Error("Failed to extract any frames from video");
    }

    return frames;
}

// ================================================================
//  BEDROCK INVOCATION
// ================================================================

/**
 * Send a single base64-encoded frame to Bedrock Nova Lite.
 * Returns parsed JSON with 4-key analysis.
 */
async function invokeBedrock(frameBase64, format) {
    console.log(`[Bedrock] Invoking ${MODEL_ID} with ${format} frame (${(frameBase64.length * 0.75 / 1024).toFixed(0)}KB)`);

    const imageBytes = Buffer.from(frameBase64, "base64");

    const command = new ConverseCommand({
        modelId: MODEL_ID,
        messages: [
            {
                role: "user",
                content: [
                    {
                        image: {
                            format: format,
                            source: { bytes: imageBytes }
                        }
                    },
                    {
                        text: ANALYSIS_PROMPT
                    }
                ]
            }
        ],
        inferenceConfig: {
            maxTokens: 120,
            temperature: 0.1
        }
    });

    const response = await bedrock.send(command);

    // Extract text from response
    let rawText = "";
    const outputContent = response.output?.message?.content || [];
    for (const block of outputContent) {
        if (block.text) rawText += block.text;
    }

    console.log(`[Bedrock] Raw response: ${rawText.substring(0, 200)}`);

    // Clean markdown fencing if present
    let cleaned = rawText.trim();
    if (cleaned.startsWith("```")) {
        const lines = cleaned.split("\n");
        cleaned = lines.filter(l => !l.trim().startsWith("```")).join("\n");
    }

    try {
        return JSON.parse(cleaned);
    } catch (e) {
        console.error(`[Bedrock] JSON parse failed: ${cleaned}`);
        // Return safe defaults if Nova returns garbage
        return {
            people_trapped: false,
            infrastructure_damage: false,
            severity: "medium",
            submergence_ratio: 0.5
        };
    }
}

// ================================================================
//  OUTPUT FORMATTING
// ================================================================

/**
 * Aggregate results from multiple frames into a single strict 4-key output.
 * 
 * Strategy:
 *   - Booleans: OR (if ANY frame says true, final = true)
 *   - severity: worst-case (high > medium > low)
 *   - submergence_ratio: average across frames, clamped [0, 1]
 */
function formatAnalysisOutput(frameResults) {
    const severityRank = { low: 0, medium: 1, high: 2 };

    let peopleTrap = false;
    let infraDamage = false;
    let worstSeverity = "low";
    let ratioSum = 0;
    let ratioCount = 0;

    for (const result of frameResults) {
        if (result.people_trapped === true) peopleTrap = true;
        if (result.infrastructure_damage === true) infraDamage = true;

        const sev = String(result.severity || "low").toLowerCase();
        if ((severityRank[sev] ?? -1) > (severityRank[worstSeverity] ?? -1)) {
            worstSeverity = sev;
        }

        const ratio = parseFloat(result.submergence_ratio);
        if (!isNaN(ratio)) {
            ratioSum += ratio;
            ratioCount++;
        }
    }

    // Clamp submergence ratio to [0, 1]
    const avgRatio = ratioCount > 0 ? ratioSum / ratioCount : 0;
    const clampedRatio = Math.round(Math.min(1, Math.max(0, avgRatio)) * 100) / 100;

    // Validate severity
    if (!["low", "medium", "high"].includes(worstSeverity)) {
        worstSeverity = "medium";
    }

    return {
        people_trapped: peopleTrap,
        infrastructure_damage: infraDamage,
        severity: worstSeverity,
        submergence_ratio: clampedRatio
    };
}

// ================================================================
//  LAMBDA HANDLER
// ================================================================

export const handler = async (event) => {
    console.log("[processFloodAI] Event received:", JSON.stringify(event).substring(0, 500));

    try {
        // Extract S3 key from the event
        const record = event.Records?.[0];
        if (!record) throw new Error("No S3 event record found");

        const bucket = record.s3.bucket.name;
        const key = decodeURIComponent(record.s3.object.key.replace(/\+/g, " "));

        console.log(`[processFloodAI] Processing: s3://${bucket}/${key}`);

        // Extract UUID from key: media/<uuid>.ext → <uuid>
        const filename = key.split("/").pop(); // e.g. "abc-123.mp4"
        const uuid = filename.replace(/\.[^.]+$/, ""); // "abc-123"

        // Step 1: Frame Extraction
        const frames = await frameExtraction(bucket, key);
        console.log(`[processFloodAI] Extracted ${frames.length} frame(s)`);

        // Step 2: Invoke Bedrock for each frame
        const frameResults = [];
        for (let i = 0; i < frames.length; i++) {
            console.log(`[processFloodAI] Analyzing frame ${i + 1}/${frames.length}...`);
            const result = await invokeBedrock(frames[i].base64, frames[i].format);
            frameResults.push(result);
        }

        // Step 3: Aggregate and format output
        const analysis = formatAnalysisOutput(frameResults);
        console.log(`[processFloodAI] Final analysis:`, JSON.stringify(analysis));

        // Step 4: Write to S3 analysis/ prefix
        const analysisKey = `analysis/${uuid}.json`;
        await s3.send(new PutObjectCommand({
            Bucket: BUCKET,
            Key: analysisKey,
            Body: JSON.stringify(analysis),
            ContentType: "application/json"
        }));

        console.log(`[processFloodAI] Result written to s3://${BUCKET}/${analysisKey}`);

        return {
            statusCode: 200,
            body: JSON.stringify({ status: "success", key: analysisKey, analysis })
        };

    } catch (error) {
        console.error("[processFloodAI] FATAL:", error);
        return {
            statusCode: 500,
            body: JSON.stringify({ status: "error", message: error.message })
        };
    }
};
