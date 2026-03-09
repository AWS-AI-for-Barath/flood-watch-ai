import { LambdaClient, UpdateFunctionCodeCommand } from "@aws-sdk/client-lambda";
import { readFileSync } from "fs";

const lambda = new LambdaClient({ region: "us-east-1" });
const zipFile = readFileSync("function.zip");

async function deploy() {
    try {
        console.log("Uploading function.zip to processFloodAI...");
        const res = await lambda.send(new UpdateFunctionCodeCommand({
            FunctionName: "processFloodAI",
            ZipFile: zipFile
        }));
        console.log("Success! Last Modified:", res.LastModified);
    } catch (e) {
        console.error(e);
    }
}
deploy();
