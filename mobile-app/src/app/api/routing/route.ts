import { NextResponse } from 'next/server';

const ROUTER_API_URL = process.env.NEXT_PUBLIC_ROUTER_API_URL || "https://gldtyb3ale.execute-api.us-east-1.amazonaws.com/route";

export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url);
        const start = searchParams.get('start');
        const goal = searchParams.get('goal');

        const response = await fetch(`${ROUTER_API_URL}?start=${start}&goal=${goal}`, { cache: 'no-store' });
        const data = await response.json();

        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
