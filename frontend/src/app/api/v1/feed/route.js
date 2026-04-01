import { NextResponse } from 'next/server';

//Proxy to backend API
export async function GET() {
    try {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002';

        //Added a 10 second timeout to prevent hanging
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch(`${backendUrl}/api/v1/feed`, {
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();
        return NextResponse.json(data, { status: 200 });
    } catch (error) {
        console.error('Error fetching from backend:', error);
        //Returns empty feed instead of error to prevent UI break
        return NextResponse.json({ success: true, count: 0, videos: [] }, { status: 200 });
    }
}