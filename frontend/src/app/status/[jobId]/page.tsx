"use client";

import { useEffect, useState, useCallback, use, useRef } from 'react';
import Image from 'next/image';
import styles from '../Status.module.css';
import { Navbar } from '../../components/Navbar';

// Status calls go through the Next.js proxy (/api/v1/status/...)
// which handles camelCase transformation. BACKEND is used only for admin calls.
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || '';

interface JobStatus {
    jobId: string;
    status: string;
    progress: number;
    videoUrl: string | null;
    thumbnailUrl: string | null;
    title: string | null;
}

type AgentState = 'idle' | 'active' | 'retry' | 'done';

interface FixedAgent {
    key: string;
    name: string;
    role: string;
    activeLabel: (s: string) => string;
    doneLabel: string;
    activeAt: number;
    doneAfter: number;
}

const TOP_AGENTS: FixedAgent[] = [
    {
        key: 'watchman',
        name: 'Watchman',
        role: 'Pre-flight',
        activeLabel: () => 'Verifying APIs & FFmpeg...',
        doneLabel: 'Environment OK',
        activeAt: 1,
        doneAfter: 1,
    },
    {
        key: 'director',
        name: 'Director',
        role: 'Scripting',
        activeLabel: () => 'Writing script & visual bible...',
        doneLabel: 'Script ready',
        activeAt: 2,
        doneAfter: 2,
    },
];

const BOTTOM_AGENTS: FixedAgent[] = [
    {
        key: 'auditor',
        name: 'Auditor',
        role: 'Validating',
        activeLabel: (s) => s === 'agent_auditor_retry' ? 'Retrying failed output...' : 'Validating outputs...',
        doneLabel: 'Outputs valid',
        activeAt: 4,
        doneAfter: 4,
    },
    {
        key: 'editor',
        name: 'Editor',
        role: 'Stitching',
        activeLabel: (s) => s === 'agent_uploading' ? 'Uploading to R2...' : 'Stitching with FFmpeg...',
        doneLabel: 'Video ready',
        activeAt: 5,
        doneAfter: 5,
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
    if (status.startsWith('agent_director_slides_')) return 3;
    if (status.startsWith('agent_artist_slide')) return 3; // covers both singular and batch
    return STATUS_ORDER[status] ?? 0;
}

// Parse active slide numbers from status string.
// Singular:  agent_artist_slide_5      → Set{5}
// Batch:     agent_artist_slides_4,5,6 → Set{4,5,6}
function parseActiveSlides(status: string): Set<number> {
    if (status.startsWith('agent_artist_slides_')) {
        const nums = status.slice('agent_artist_slides_'.length).split(',').map(Number).filter(n => n > 0);
        return new Set(nums);
    }
    if (status.startsWith('agent_artist_slide_')) {
        const n = parseInt(status.slice('agent_artist_slide_'.length), 10);
        return n > 0 ? new Set([n]) : new Set();
    }
    return new Set();
}

function getFixedAgentState(agent: FixedAgent, statusOrder: number, status: string): AgentState {
    if (statusOrder > agent.doneAfter) return 'done';
    if (statusOrder === agent.activeAt) {
        if (agent.key === 'auditor' && status === 'agent_auditor_retry') return 'retry';
        return 'active';
    }
    return 'idle';
}

export default function StatusPage({ params }: { params: Promise<{ jobId: string }> }) {
    const unwrappedParams = use(params);
    const jobId = unwrappedParams.jobId;

    const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [videoTitle, setVideoTitle] = useState('');
    const [titleDirty, setTitleDirty] = useState(false);
    const [titleSaved, setTitleSaved] = useState(false);

    const [showLog, setShowLog] = useState(false);
    const [logLines, setLogLines] = useState<string[]>([]);

    // slide tracking — persists across polls
    const [totalSlides, setTotalSlides] = useState(0);
    const [maxSlidesSeen, setMaxSlidesSeen] = useState(0);
    // context_refs: { slideIndex_0based: [referencedSlideIndex_0based, ...] }
    const [contextRefs, setContextRefs] = useState<Record<number, number[]>>({});

    const mainVideoRef = useRef<HTMLVideoElement>(null);
    const modalVideoRef = useRef<HTMLVideoElement>(null);
    const logEndRef = useRef<HTMLDivElement>(null);

    const fetchStatus = useCallback(async () => {
        if (!jobId) { setError("Job ID is missing."); return; }
        try {
            const res = await fetch(`/api/v1/status/${jobId}`);
            if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
            const data: JobStatus = await res.json();
            setJobStatus(data);

            const s = data.status;

            // parse Director's "slide count + context refs" signal
            // format: agent_director_slides_8:1>0,3>0,5>3
            if (s.startsWith('agent_director_slides_')) {
                const rest = s.slice('agent_director_slides_'.length);
                const [slidesPart, refsPart] = rest.split(':');
                const n = parseInt(slidesPart, 10);
                if (n > 0) setTotalSlides(n);
                if (refsPart) {
                    const refs: Record<number, number[]> = {};
                    refsPart.split(',').forEach(pair => {
                        const [from, to] = pair.split('>').map(Number);
                        if (!isNaN(from) && !isNaN(to)) {
                            if (!refs[from]) refs[from] = [];
                            refs[from].push(to);
                        }
                    });
                    setContextRefs(refs);
                }
            }

            // track the highest slide number ever seen (fixes graph disappearing after artist phase)
            if (s.startsWith('agent_artist_slide')) {
                const parsed = parseActiveSlides(s);
                if (parsed.size > 0) setMaxSlidesSeen(prev => Math.max(prev, ...parsed));
            }

            // initialize title from DB if available
            if (data.title) {
                setVideoTitle(data.title);
            } else if (!videoTitle && data.status === 'done') {
                setVideoTitle(`VIDEO #${jobId.slice(0, 4).toUpperCase()}`);
            }
        } catch (err) {
            console.error("Polling error:", err);
            setError("Could not retrieve job status.");
        }
    }, [jobId]);

    const fetchLogs = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/v1/status/${jobId}/logs`);
            if (!res.ok) return;
            const data = await res.json();
            setLogLines(data.logs || []);
        } catch { /* silent */ }
    }, [jobId]);

    // auto-scroll log to bottom when new lines arrive
    useEffect(() => {
        if (showLog && logEndRef.current) {
            logEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logLines, showLog]);

    // poll logs while log panel is open and job is still running
    useEffect(() => {
        if (!showLog) return;
        fetchLogs();
        if (jobStatus?.status === 'done' || jobStatus?.status === 'failed') return;
        const id = setInterval(fetchLogs, 5000);
        return () => clearInterval(id);
    }, [showLog, fetchLogs, jobStatus?.status]);

    useEffect(() => {
        let intervalId: NodeJS.Timeout | undefined;
        if (jobStatus?.status === 'done' || jobStatus?.status === 'failed') return () => { };

        const initialDelayTimer = setTimeout(() => {
            fetchStatus();
            intervalId = setInterval(fetchStatus, 5000);
        }, 2000);

        return () => {
            clearTimeout(initialDelayTimer);
            if (intervalId) clearInterval(intervalId);
        };
    }, [fetchStatus, jobStatus?.status]);

    // initialize title once we get a done job
    useEffect(() => {
        if (jobStatus?.status === 'done' && !videoTitle) {
            setVideoTitle(jobStatus.title || `VIDEO #${jobId.slice(0, 4).toUpperCase()}`);
        }
    }, [jobStatus?.status]);


    // ---- DONE STATE ----
    if (jobStatus?.status === 'done' && jobStatus.videoUrl) {

        const handleSaveTitle = async () => {
            if (!titleDirty || !videoTitle.trim()) return;
            try {
                await fetch(`/api/v1/status/${jobId}/title`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: videoTitle.trim() })
                });
                setTitleDirty(false);
                setTitleSaved(true);
                setTimeout(() => setTitleSaved(false), 2000);
            } catch { /* silent fail */ }
        };

        const handleDownload = async () => {
            if (!jobStatus.videoUrl) return;
            const safeName = (videoTitle || 'keyframe_video').replace(/[^a-zA-Z0-9_\-\s]/g, '').trim();
            try {
                const response = await fetch(jobStatus.videoUrl);
                if (!response.ok) throw new Error('fetch failed');
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${safeName}.mp4`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch {
                window.open(jobStatus.videoUrl, '_blank');
            }
        };

        const handleOpenModal = () => {
            const mainVideo = mainVideoRef.current;
            if (mainVideo) {
                mainVideo.pause();
                setIsModalOpen(true);
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
                mainVideo.currentTime = modalVideo.currentTime;
                const wasPlaying = !modalVideo.paused;
                setIsModalOpen(false);
                if (wasPlaying) setTimeout(() => mainVideo.play(), 50);
            } else {
                setIsModalOpen(false);
            }
        };

        const handleSubmitToCommunity = async () => {
            await handleSaveTitle();
            alert('Video submitted to community!');
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
                                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                                >
                                    Your browser does not support the video tag.
                                </video>
                            </div>

                            <div className={styles.controlsRow}>
                                <div className={styles.titleRow}>
                                    <input
                                        type="text"
                                        value={videoTitle}
                                        onChange={(e) => { setVideoTitle(e.target.value); setTitleDirty(true); setTitleSaved(false); }}
                                        onBlur={handleSaveTitle}
                                        className={styles.videoTitleInput}
                                        placeholder="Name this video..."
                                    />
                                    {titleSaved && <span className={styles.savedBadge}>Saved</span>}
                                </div>
                                <button
                                    onClick={handleDownload}
                                    className={styles.iconButton}
                                    title="Download video"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" x2="12" y1="15" y2="3" /></svg>
                                </button>
                                <button className={styles.iconButton} onClick={handleOpenModal} title="View fullscreen">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></svg>
                                </button>
                            </div>

                            <button className={styles.submitButton} onClick={handleSubmitToCommunity}>
                                Submit Video to Community
                            </button>
                        </div>
                    </div>

                    <div className={styles.logSection}>
                        <button
                            className={styles.logToggleButton}
                            onClick={() => setShowLog(v => !v)}
                        >
                            {showLog ? 'Hide Log' : 'Show Log'}
                        </button>
                        {showLog && (
                            <div className={styles.logPanel}>
                                {logLines.length === 0
                                    ? <span className={styles.logEmpty}>No log entries yet.</span>
                                    : logLines.map((line, i) => <div key={i} className={styles.logLine}>{line}</div>)
                                }
                                <div ref={logEndRef} />
                            </div>
                        )}
                    </div>

                    {isModalOpen && (
                        <div className={styles.modalOverlay} onClick={handleCloseModal}>
                            <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
                                <button className={styles.closeButton} onClick={handleCloseModal}>✕</button>
                                <video
                                    ref={modalVideoRef}
                                    controls
                                    src={jobStatus.videoUrl}
                                    style={{ width: '100%', maxHeight: '80vh', objectFit: 'contain' }}
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


    // ---- PROCESSING STATE ----
    const currentStatus = jobStatus?.status || 'queued';
    const statusOrder = getStatusOrder(currentStatus);

    const activeSlides = parseActiveSlides(currentStatus);
    const batchMin = activeSlides.size > 0 ? Math.min(...activeSlides) : 0;

    // displaySlides: use totalSlides if known, else maxSlidesSeen — never goes back to 0
    const displaySlides = totalSlides > 0 ? totalSlides : maxSlidesSeen;

    const inArtistPhase = statusOrder === 3;
    const pastArtistPhase = statusOrder > 3;

    // which slides are being "consulted" by all currently active slides
    const consultingSet = new Set<number>();
    if (inArtistPhase && activeSlides.size > 0) {
        activeSlides.forEach(slideNum => {
            (contextRefs[slideNum - 1] || []).forEach(ref => consultingSet.add(ref));
        });
    }

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

                    <p className={styles.statusText}>Generating Video</p>

                    <div className={styles.agentGraph}>

                        {/* Top fixed agents */}
                        {TOP_AGENTS.map((agent, i) => {
                            const state = getFixedAgentState(agent, statusOrder, currentStatus);
                            const label = state === 'done' ? agent.doneLabel
                                : state === 'active' ? agent.activeLabel(currentStatus)
                                : agent.role;
                            return (
                                <div key={agent.key} className={styles.agentGraphRow}>
                                    <div className={`${styles.agentNode} ${styles[`agentNode_${state}`]}`}>
                                        <div className={styles.agentNodeIndicator} />
                                        <div className={styles.agentNodeName}>{agent.name}</div>
                                        <div className={styles.agentNodeLabel}>{label}</div>
                                    </div>
                                    {i < TOP_AGENTS.length - 1 && (
                                        <div className={`${styles.agentEdge} ${state === 'done' || statusOrder > agent.activeAt ? styles.agentEdgeActive : ''}`} />
                                    )}
                                    {i === TOP_AGENTS.length - 1 && (
                                        <div className={`${styles.agentEdge} ${statusOrder > 2 ? styles.agentEdgeActive : ''}`} />
                                    )}
                                </div>
                            );
                        })}

                        {/* Per-slide agent nodes */}
                        {displaySlides > 0 && (
                            <div className={styles.slideAgentSection}>
                                <div className={styles.slideAgentGrid}>
                                    {Array.from({ length: displaySlides }, (_, i) => {
                                        const slideNum = i + 1;
                                        let slideState: AgentState = 'idle';
                                        if (pastArtistPhase) {
                                            slideState = 'done';
                                        } else if (inArtistPhase) {
                                            if (batchMin > 0 && slideNum < batchMin) slideState = 'done';
                                            else if (activeSlides.has(slideNum)) slideState = 'active';
                                        }

                                        const isConsulting = !pastArtistPhase && consultingSet.has(i);

                                        // Build label
                                        let label = 'Waiting';
                                        if (isConsulting) label = 'Consulted';
                                        else if (slideState === 'active') label = 'Painting...';
                                        else if (slideState === 'done') label = 'Done';

                                        return (
                                            <div key={slideNum} className={styles.slideAgentRow}>
                                                <div className={[
                                                    styles.agentNode,
                                                    styles.slideAgentNode,
                                                    styles[`agentNode_${slideState}`],
                                                    isConsulting ? styles.agentNode_consulting : ''
                                                ].filter(Boolean).join(' ')}>
                                                    <div className={styles.agentNodeIndicator} />
                                                    <div className={styles.slideAgentNum}>S{slideNum}</div>
                                                    <div className={styles.agentNodeLabel}>{label}</div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                {/* Show context legend if any consulting is happening */}
                                {consultingSet.size > 0 && activeSlides.size > 0 && (
                                    <p className={styles.contextHint}>
                                        Slide{activeSlides.size > 1 ? 's' : ''} {[...activeSlides].sort((a,b)=>a-b).join(', ')} requesting context from slide{consultingSet.size > 1 ? 's' : ''} {[...consultingSet].map(n => n + 1).join(', ')}
                                    </p>
                                )}
                                <div className={`${styles.agentEdge} ${pastArtistPhase || (inArtistPhase && activeSlides.size > 0 && Math.max(...activeSlides) === displaySlides) ? styles.agentEdgeActive : ''}`} />
                            </div>
                        )}

                        {/* Fallback edge if slides not yet revealed */}
                        {displaySlides === 0 && statusOrder > 2 && (
                            <div className={`${styles.agentEdge} ${styles.agentEdgeActive}`} />
                        )}

                        {/* Bottom fixed agents */}
                        {BOTTOM_AGENTS.map((agent, i) => {
                            const state = getFixedAgentState(agent, statusOrder, currentStatus);
                            const label = state === 'done' ? agent.doneLabel
                                : state === 'active' || state === 'retry' ? agent.activeLabel(currentStatus)
                                : agent.role;
                            return (
                                <div key={agent.key} className={styles.agentGraphRow}>
                                    <div className={`${styles.agentNode} ${styles[`agentNode_${state}`]}`}>
                                        <div className={styles.agentNodeIndicator} />
                                        <div className={styles.agentNodeName}>{agent.name}</div>
                                        <div className={styles.agentNodeLabel}>{label}</div>
                                    </div>
                                    {i < BOTTOM_AGENTS.length - 1 && (
                                        <div className={`${styles.agentEdge} ${state === 'done' || statusOrder > agent.activeAt ? styles.agentEdgeActive : ''}`} />
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {error && <p className={styles.errorText}>{error}</p>}

                    <div className={styles.logSection}>
                        <button
                            className={styles.logToggleButton}
                            onClick={() => setShowLog(v => !v)}
                        >
                            {showLog ? 'Hide Log' : 'Show Log'}
                        </button>
                        {showLog && (
                            <div className={styles.logPanel}>
                                {logLines.length === 0
                                    ? <span className={styles.logEmpty}>Waiting for log entries...</span>
                                    : logLines.map((line, i) => <div key={i} className={styles.logLine}>{line}</div>)
                                }
                                <div ref={logEndRef} />
                            </div>
                        )}
                    </div>
                </div>
            </main>
        </>
    );
}
