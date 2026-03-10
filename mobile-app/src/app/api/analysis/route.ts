import { NextResponse } from 'next/server';
import aws4 from 'aws4';
import { fromNodeProviderChain } from '@aws-sdk/credential-providers';

export const runtime = 'nodejs';

const BUCKET = process.env.BUCKET_NAME || "floodwatch-uploads";
const REGION = process.env.FLOODWATCH_AWS_REGION || process.env.NEXT_PUBLIC_FLOODWATCH_AWS_REGION || "us-east-1";

export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url);
        const uuid = searchParams.get('uuid');

        if (!uuid) {
            return NextResponse.json({ error: "Missing uuid parameter" }, { status: 400 });
        }

        const analysisKey = `analysis/mobile-${uuid}.json`;

        // Create standard AWS HTTP request options for S3 REST API
        const opts: any = {
            host: `${BUCKET}.s3.${REGION}.amazonaws.com`,
            path: `/${analysisKey}`,
            service: 's3',
            region: REGION,
            method: 'GET',
            headers: {}
        };

        // Fetch IAM Role credentials dynamically from the Amplify Lambda container
        const provider = fromNodeProviderChain();
        const credentials = await provider();

        // Sign the request natively using the temporary IAM STS tokens
        aws4.sign(opts, {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken
        });

        // Perform raw HTTPS fetch from S3
        const s3Url = `https://${opts.host}${opts.path}`;
        const s3Res = await fetch(s3Url, {
            method: opts.method,
            headers: opts.headers,
            cache: 'no-store'
        });

        if (s3Res.status === 404 || s3Res.status === 403) {
            // S3 returns 403 if it doesn't exist but IAM lacks ListBucket
            return NextResponse.json({ status: "pending" }, { status: 200 });
        }

        if (!s3Res.ok) {
            const errTxt = await s3Res.text();
            throw new Error(`S3 returned HTTP ${s3Res.status}: ${errTxt}`);
        }

        const data = await s3Res.json();
        return NextResponse.json({ status: "complete", data }, { status: 200 });

    } catch (error: any) {
        console.error("Analysis Poll Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
