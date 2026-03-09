import { NextResponse } from 'next/server';

const PRESIGN_API_URL = process.env.NEXT_PUBLIC_PRESIGN_API_URL || "https://150zje9iz6.execute-api.us-east-1.amazonaws.com/generate-upload-url";

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const response = await fetch(PRESIGN_API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            cache: 'no-store'
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
