import { NextResponse } from 'next/server';

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

        // Fetch directly from public S3 URL (bucket policy allows public read on analysis/*)
        const s3Url = `https://${BUCKET}.s3.${REGION}.amazonaws.com/${analysisKey}`;
        const s3Res = await fetch(s3Url, { cache: 'no-store' });

        if (s3Res.status === 404 || s3Res.status === 403) {
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
