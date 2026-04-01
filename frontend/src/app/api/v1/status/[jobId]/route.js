//src/app/api/v1/status/[JobId]/route.js
import { NextResponse } from 'next/server';

function computeProgress(status) {
    if (!status || status === 'queued') return 5;
    if (status === 'failed') return 0;
    if (status === 'done') return 100;
    if (status === 'agent_watchman_active' || status === 'processing') return 12;
    if (status === 'agent_director_writing') return 25;
    if (status === 'agent_auditor_checking') return 72;
    if (status === 'agent_auditor_retry') return 75;
    if (status === 'agent_stitching') return 82;
    if (status === 'agent_uploading') return 92;

    // agent_artist_slide_N — slides span 30%–70%
    if (status.startsWith('agent_artist_slide_')) {
        const slideNum = parseInt(status.split('_').pop(), 10);
        if (!isNaN(slideNum)) {
            return Math.min(30 + slideNum * 4, 70);
        }
    }

    return 10;
}

export async function GET(request, { params }) {
    const unwrappedParams = await params;
    const jobId = unwrappedParams.jobId;

    try {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002';

        const response = await fetch(`${backendUrl}/api/v1/status/${jobId}`);

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();

        // Transform snake_case to camelCase for frontend
        const transformedData = {
            jobId: data.id,
            status: data.status,
            progress: computeProgress(data.status),
            videoUrl: data.video_url,
            thumbnailUrl: data.thumbnail_url
        };

        return NextResponse.json(transformedData, { status: 200 });
    } catch (error) {
        console.error('Error fetching status from backend:', error);
        return NextResponse.json({
            error: 'Failed to get job status',
            jobId,
            status: 'failed',
            progress: 0
        }, { status: 500 });
    }
}
