"use client";

import { useEffect, useState, useCallback, use, useRef } from 'react';
import Image from 'next/image';
import styles from '../Status.module.css';
import { Navbar } from '../../components/Navbar';


interface JobStatus {
    jobId: string;
    status: string;
    progress: number;
    videoUrl: string | null;
    thumbnailUrl: string | null;
}

type AgentState = 'idle' | 'active' | 'retry' | 'done';

interface AgentCard {
    key: string;
    name: string;
    role: string;
    activeLabel: (s: string) => string;
    doneLabel: string;
}

const AGENT_CARDS: AgentCard[] = [
    {
        key: 'watchman',
        name: 'Watchman',
        role: 'Pre-flight',
        activeLabel: () => 'Verifying APIs & FFmpeg...',
        doneLabel: 'Environment OK',
    },
    {
        key: 'director',
        name: 'Director',
        role: 'Scripting',
        activeLabel: () => 'Writing script & visual bible...',
        doneLabel: 'Script ready',
    },
    {
        key: 'artist',
        name: 'Artist',
        role: 'Generating',
        activeLabel: (s) => s.startsWith('agent_artist_slide_')
            ? `Painting slide ${s.split('_').pop()}...`
            : 'Generating images...',
        doneLabel: 'Images ready',
    },
    {
        key: 'auditor',
        name: 'Auditor',
        role: 'Validating',
        activeLabel: (s) => s === 'agent_auditor_retry' ? 'Retrying failed output...' : 'Validating outputs...',
        doneLabel: 'Outputs valid',
    },
    {
        key: 'editor',
        name: 'Editor',
        role: 'Stitching',
        activeLabel: (s) => s === 'agent_uploading' ? 'Uploading to R2...' : 'Stitching with FFmpeg...',
        doneLabel: 'Video ready',
    },
];

const STATUS_ORDER: Record<string, number> = {
    queued: 0, processing: 0,
    agent_watchman_active: 1,
    agent_director_writing: 2,
    agent_auditor_checking: 4,
    agent_auditor_retry: 4,
    agent_stitching: 5,
    agent_uploading: 5,
    done: 6,
};

function getStatusOrder(status: string): number {
    if (status.startsWith('agent_artist_slide_')) return 3;
    return STATUS_ORDER[status] ?? 0;
}

function getAgentStates(status: string): Record<string, AgentState> {
    const agentOrder = ['watchman', 'director', 'artist', 'auditor', 'editor'];
    const agentThresholds = [1, 2, 3, 4, 5];
    const current = getStatusOrder(status);
    const isRetry = status === 'agent_auditor_retry';

    const states: Record<string, AgentState> = {};
    agentOrder.forEach((key, i) => {
        const threshold = agentThresholds[i];
        if (current > threshold) states[key] = 'done';
        else if (current === threshold) states[key] = (isRetry && key === 'auditor') ? 'retry' : 'active';
        else states[key] = 'idle';
    });
    return states;
}

export default function StatusPage({ params }: { params: Promise<{ jobId: string }> }) {
    //Unwraps params using React.use()
    const unwrappedParams = use(params);
    const jobId = unwrappedParams.jobId;

    const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [videoTitle, setVideoTitle] = useState(`VIDEO NAME #${jobId.slice(0, 4)}`);

    const mainVideoRef = useRef<HTMLVideoElement>(null);
    const modalVideoRef = useRef<HTMLVideoElement>(null);

    const fetchStatus = useCallback(async () => {
        if (!jobId) {
            setError("Job ID is missing.");
            return;
        }
        try {
            const res = await fetch(`/api/v1/status/${jobId}`);
            if (!res.ok) {

                throw new Error(`Status check failed: ${res.status}`);
            }
            const data: JobStatus = await res.json();
            setJobStatus(data);
        } catch (err) {
            console.error("Polling error:", err);
            setError("Could not retrieve job status.");
        }
    }, [jobId]);

    useEffect(() => {
        let intervalId: NodeJS.Timeout | undefined;

        
        //If job is already done:
        if (jobStatus?.status === 'done' || jobStatus?.status === 'failed') {
            return () => { }; // Return an empty cleanup function, essentially stopping the loop.
        }

        // 1.Initial Delay Timer (2 seconds)
        const initialDelayTimer = setTimeout(() => {
            fetchStatus();

            // 2. Start Polling Interval (Only starts if status is still not complete/error)
            intervalId = setInterval(fetchStatus, 5000);

        }, 2000);


        // 3. Global Cleanup Function
        return () => {
            clearTimeout(initialDelayTimer);
            if (intervalId) {
                clearInterval(intervalId);
            }
        };

    }, [fetchStatus, jobStatus?.status]);


    if (jobStatus?.status === 'done' && jobStatus.videoUrl) {
        const handleDownload = () => {
            if (jobStatus.videoUrl) {
                window.open(jobStatus.videoUrl, '_blank');
            }
        };

        const handleOpenModal = () => {
            const mainVideo = mainVideoRef.current;
            if (mainVideo) {
                // Pause main video and open modal
                mainVideo.pause();
                setIsModalOpen(true);

                // After modal opens, sync time with modal video
                setTimeout(() => {
                    const modalVideo = modalVideoRef.current;
                    if (modalVideo) {
                        modalVideo.currentTime = mainVideo.currentTime;
                        modalVideo.play();
                    }
                }, 50);
            }
        };

        const handleCloseModal = () => {
            const modalVideo = modalVideoRef.current;
            const mainVideo = mainVideoRef.current;

            if (modalVideo && mainVideo) {
                // Sync time back to main video
                mainVideo.currentTime = modalVideo.currentTime;
                const wasPlaying = !modalVideo.paused;

                setIsModalOpen(false);

                // Resume main video if modal was playing
                if (wasPlaying) {
                    setTimeout(() => {
                        mainVideo.play();
                    }, 50);
                }
            } else {
                setIsModalOpen(false);
            }
        };

        const handleSubmitToCommunity = async () => {
            try {
                // TODO: Implement API call to submit video to community
                alert('Video submitted to community!');
            } catch (err) {
                alert('Failed to submit to community');
            }
        };

        return (
            <>
                <Navbar activePath="/" />
                <main className={styles.mainContainer}>

                    <div className={styles.completeViewContainer}>

                        <div className={styles.videoCard}>

                            <div className={styles.videoWrapper}>
                                <video
                                    ref={mainVideoRef}
                                    controls
                                    src={jobStatus.videoUrl}
                                    poster={jobStatus.thumbnailUrl || undefined}
                                    style={{
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'contain'
                                    }}
                                >
                                    Your browser does not support the video tag.
                                </video>
                            </div>


                            <div className={styles.controlsRow}>

                                <input
                                    type="text"
                                    value={videoTitle}
                                    onChange={(e) => setVideoTitle(e.target.value)}
                                    className={styles.videoTitleInput}
                                />

                                <button
                                    onClick={handleDownload}
                                    className={styles.iconButton}
                                    title="Open in new tab"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" x2="12" y1="15" y2="3" /></svg>
                                </button>

                                <button
                                    className={styles.iconButton}
                                    onClick={handleOpenModal}
                                    title="View fullscreen"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></svg>
                                </button>
                            </div>

                            <button
                                className={styles.submitButton}
                                onClick={handleSubmitToCommunity}
                            >
                                Submit Video to Community
                            </button>
                        </div>
                    </div>

                    {/* Modal for fullscreen video */}
                    {isModalOpen && (
                        <div className={styles.modalOverlay} onClick={handleCloseModal}>
                            <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
                                <button
                                    className={styles.closeButton}
                                    onClick={handleCloseModal}
                                >
                                    ✕
                                </button>
                                <video
                                    ref={modalVideoRef}
                                    controls
                                    src={jobStatus.videoUrl}
                                    style={{
                                        width: '100%',
                                        maxHeight: '80vh',
                                        objectFit: 'contain'
                                    }}
                                >
                                    Your browser does not support the video tag.
                                </video>
                            </div>
                        </div>
                    )}
                </main>
            </>
        );
    }


    // RENDER 2: PROCESSING STATE
    const currentStatus = jobStatus?.status || 'queued';
    const agentStates = getAgentStates(currentStatus);

    return (
        <>
            <main className={styles.mainContainer}>
                <div className={styles.processArea}>

                    <div className={styles.logoIcon}>
                        <Image
                            src="/assets/Logo_Transparent.png"
                            alt="KeyFrame Logo"
                            width={128}
                            height={128}
                            style={{ width: '100%', height: '100%' }}
                        />
                    </div>

                    <p className={styles.statusText}>AGENTIC PIPELINE RUNNING</p>

                    {/* Agent graph */}
                    <div className={styles.agentGraph}>
                        {AGENT_CARDS.map((agent, i) => {
                            const state = agentStates[agent.key];
                            const label = state === 'done'
                                ? agent.doneLabel
                                : state === 'active' || state === 'retry'
                                    ? agent.activeLabel(currentStatus)
                                    : agent.role;
                            return (
                                <div key={agent.key} className={styles.agentGraphRow}>
                                    <div className={`${styles.agentNode} ${styles[`agentNode_${state}`]}`}>
                                        <div className={styles.agentNodeIndicator} />
                                        <div className={styles.agentNodeName}>{agent.name}</div>
                                        <div className={styles.agentNodeLabel}>{label}</div>
                                    </div>
                                    {i < AGENT_CARDS.length - 1 && (
                                        <div className={`${styles.agentEdge} ${agentStates[AGENT_CARDS[i + 1].key] !== 'idle' ? styles.agentEdgeActive : ''}`} />
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {error && <p className={styles.errorText}>{error}</p>}
                </div>
            </main>
        </>
    );
}
