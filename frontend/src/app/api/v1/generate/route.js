import { NextResponse } from 'next/server';

export async function POST(request) {
    try {
        const body = await request.json();
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002';

        const response = await fetch(`${backendUrl}/api/v1/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();
        return NextResponse.json(data, { status: 202 });
    } catch (error) {
        console.error('Error submitting job to backend:', error);
        return NextResponse.json(
            { error: 'Failed to submit job' },
            { status: 500 }
        );
    }
}