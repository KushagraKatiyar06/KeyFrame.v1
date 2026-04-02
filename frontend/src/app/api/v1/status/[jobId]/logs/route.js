import { NextResponse } from 'next/server';

export async function GET(request, { params }) {
    const unwrappedParams = await params;
    const jobId = unwrappedParams.jobId;

    try {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002';
        const response = await fetch(`${backendUrl}/api/v1/status/${jobId}/logs`);

        if (!response.ok) {
            return NextResponse.json({ logs: [] }, { status: 200 });
        }

        const data = await response.json();
        return NextResponse.json({ logs: data.logs || [] }, { status: 200 });
    } catch (error) {
        console.error('Error fetching logs from backend:', error);
        return NextResponse.json({ logs: [] }, { status: 200 });
    }
}
