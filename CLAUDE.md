# KeyFrame — CLAUDE.md

Auto-loaded context for Claude Code. Read this before touching any file.

---

## What this project is

AI slideshow generator. User submits a prompt + style → gets back a ~1min video with images, voiceover, and captions. Target cost: ~$0.20/video.

**Styles:** Educational, Storytelling, Meme

**Live site:** https://keyframe-one.vercel.app

---

## Current goal: Agentic Refactor (`agentic_enhancement` branch)

Move from a linear try/except pipeline to a **State Machine** with named agent roles, granular UI feedback, and visual continuity across slides.

### Agent roles

| Agent | Responsibility |
|---|---|
| **The Watchman** (Sentinel) | Pre-flight: verify FFmpeg exists and is executable. Canary pings to OpenAI, Nebius (text), Replicate, AWS — fail immediately on 401/403 to prevent partial spend. |
| **The Director** (Architect) | Generates the script + a **Global Visual Bible** (character descriptions, color palette, lighting style). |
| **The Continuity Artist** (Image Gen) | Uses a single `session_seed` across all slides. Prepends the Visual Bible to every image prompt. Each prompt references the previous frame's context. |
| **The Auditor** (Validator) | Checks images are > 0 bytes and audio durations > 0.5s. Retries the specific agent up to 3 times on failure. Cleans up temp `.mp4` segments only after confirming the final file is valid. |

### Granular status updates

`status` column in Postgres must be updated at every agent transition, e.g.:
`agent_watchman_active` → `agent_director_writing` → `agent_artist_slide_3` → `agent_auditor_checking` → `done`

### UI requirements

- **Progress bar** on the Status page: segmented — Setup → Scripting → Generating → Stitching
- **Agent Console**: component showing which agent is "thinking" with pulsing animations or log stream

---

## Architecture

```
frontend/          Next.js (port 3000) — UI + mock API routes
backend/api/       Express.js (port 3002) — job intake, Postgres, Redis queue
backend/worker/    Python Celery — full AI pipeline
bin/               ffmpeg.exe + ffprobe.exe (gitignored)
```

**Request flow:**
```
User → Next.js → POST /api/v1/generate (Express)
                       ↓
               Insert job into Postgres (status: queued)
               Push job to Redis (Celery queue)
                       ↓
               Celery worker picks up job
               1. Watchman pre-flight check
               2. Director: generate_script() + Visual Bible  — Nebius (nemotron)
               3. Continuity Artist: generate_images()        — Replicate (Flux-Schnell) ─┐ parallel
               4. Voice Over: generate_voice_over()           — Amazon Polly           ─┘
               5. Auditor: validate outputs, retry up to 3x
               4. stitch_video()                              — FFmpeg
               5. upload_files()                              — Cloudflare R2
               6. update_job_status(done)                     — Postgres
                       ↓
User polls GET /api/v1/status/:jobId → gets video_url when done
```

---

## Key files

| File | Purpose |
|---|---|
| `backend/api/index.js` | Express entry, mounts routes, initializes DB table |
| `backend/api/database.js` | All Postgres queries (insertJob, updateJobStatus, getJobById, getRecentCompletedVideos) |
| `backend/api/redis.js` | Redis client + pushJob (formats Celery-compatible message) |
| `backend/api/routes/generate.js` | POST /api/v1/generate — validates, inserts to DB, pushes to Redis |
| `backend/api/routes/status.js` | GET /api/v1/status/:jobId — polls Postgres |
| `backend/api/routes/feed.js` | GET /api/v1/feed — last 15 completed videos (5 per style) |
| `backend/worker/app.py` | Celery app init, broker = REDIS_URL |
| `backend/worker/orchestrator.py` | Main Celery task — orchestrates all pipeline steps |
| `backend/worker/script.py` | Nebius nemotron call → structured JSON script with slides |
| `backend/worker/image_generation.py` | Replicate API → Flux-Schnell image per slide |
| `backend/worker/voice_over.py` | Amazon Polly TTS per slide → binary concat (no FFmpeg) |
| `backend/worker/assemble.py` | FFmpeg: images + audio → MP4 segments → final video |
| `backend/worker/storage.py` | Upload video + thumbnail to Cloudflare R2 via boto3 |
| `backend/worker/database.py` | Python Postgres client (psycopg2) |
| `frontend/src/app/page.tsx` | Home — prompt form |
| `frontend/src/app/status/[jobId]/page.tsx` | Job status + video playback |
| `frontend/src/app/feed/page.tsx` | Community feed |

---

## Postgres schema

```sql
CREATE TABLE videos (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt       TEXT NOT NULL,
  style        TEXT NOT NULL,
  status       TEXT DEFAULT 'queued',   -- queued | processing | done | failed | agent_*
  video_url    TEXT,
  thumbnail_url TEXT,
  created_at   TIMESTAMP DEFAULT NOW()
);
```

Hosted on **Neon** (serverless Postgres). Free tier may expire.

---

## Technical specs

### Image generation (Flux-Schnell via Replicate)
- Uses `replicate` Python package with `black-forest-labs/flux-schnell` model
- Pick a random int at job start → pass as `seed` to every Replicate call
- Prepend the Visual Bible to every image prompt
- Each prompt references the previous slide's context for continuity
- Output format: jpg, aspect_ratio: 16:9

### Audio (Amazon Polly)
- Use the `generative` engine with **plain text** (generative does NOT support SSML)
- Falls back to `neural` then `standard` if a voice isn't on generative
- Voice assignment is per-slide from the script JSON (AI-assigned by the Director)
- Audio concatenation: pure Python binary concat (no FFmpeg subprocess) — already implemented

### FFmpeg
- Path resolved via `FFMPEG_PATH` env var; falls back to `<repo-root>/bin/ffmpeg.exe`
- Same for `FFPROBE_PATH` / `ffprobe`
- Temp `.mp4` segments must be deleted after stitch, but **only** if the Auditor confirms the final file is valid

---

## Environment variables

### `backend/api/.env`
```
DATABASE_URL=...   # Neon Postgres connection string
REDIS_URL=...      # Redis Cloud URL
PORT=3001
```

### `backend/worker/.env`
```
DATABASE_URL=...
REDIS_URL=...
OPENAI_API_KEY=...
NEBIUS_API_KEY=...         # used for nemotron text model (script + visual bible)
REPLICATE_API_TOKEN=...    # used for Flux-Schnell image generation
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_ACCESS_KEY_ID=...
CLOUDFLARE_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
R2_PUBLIC_DOMAIN=...
FFMPEG_PATH=...    # e.g. C:\Program Files\ffmpeg\bin\ffmpeg.exe
FFPROBE_PATH=...   # e.g. C:\Program Files\ffmpeg\bin\ffprobe.exe
```

### `frontend/.env.local`
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:3002
```

**Gotchas:**
- The `env` files (no dot) in each directory are the committed versions — dotenv won't load these. The `.env` files (with dot) are the real ones (gitignored).
- FFmpeg resolved via `FFMPEG_PATH` env var first, then `bin/ffmpeg.exe` fallback. Install via `winget install Gyan.FFmpeg` on Windows.
- Windows Smart App Control can block FFmpeg subprocess calls with `WinError 4551`. Fix: Settings → Windows Security → App & Browser Control → Smart App Control → Off.
- Free tier Redis/Postgres may go down. If `getaddrinfo ENOTFOUND` → Redis Cloud instance expired. Fix: recreate on redislabs.com or run locally with Docker.

### Local isolation + deploy safety
- Use environment isolation, not branch isolation: same code path, different env values for `local`, `staging`, and `production`.
- Keep runtime env files uncommitted (`.env.local`, `.env` with secrets); commit only `*.env.example` templates.
- Do not reuse production DB/Redis/storage/API keys for local development.
- Keep variable names consistent across environments; only values should change.
- Local-dev infrastructure changes should be additive and backward-compatible so they can be merged to `main` without breaking hosted services.
- Hosted reconfiguration is only required when runtime code introduces new required env vars or renames/removes existing ones used in production.
- Recommended flow: feature branch → local smoke test → staging deploy/validation → merge to `main`.

---

## Running locally

### Prerequisites
- Node.js v18+
- Python 3.10+ (currently using 3.14.2)
- FFmpeg: `winget install Gyan.FFmpeg`, then set `FFMPEG_PATH` + `FFPROBE_PATH` in `backend/worker/.env`

### Backend API (Terminal 1)
```bash
cd backend/api
node index.js        # reads .env automatically, runs on port 3001
```

### Python Worker (Terminal 2)
```bash
cd backend/worker
.venv/Scripts/Activate.ps1      # Windows PowerShell
# or: source .venv/bin/activate  # bash/mac
celery -A app worker --loglevel=info --pool=solo   # --pool=solo required on Windows
```

### Frontend (Terminal 3)
```bash
cd frontend
npm run dev          # runs on port 3000
```

---

## Coding standards

- **Minimal comments** — explain logic in chat, not in files. Keep existing comments as-is.
- **Legacy preservation** — keep original comments and existing spacing/indents when editing.
- **Syntax** — standard, readable Python/JS. No obscure or bleeding-edge patterns.
- **DB** — use `psycopg2` for Python Postgres updates.
- **Env** — use `python-dotenv` / `dotenv` for env management.

---

## External services (all free tiers — may expire)

| Service | Used for | Dashboard |
|---|---|---|
| Neon | Postgres DB | console.neon.tech |
| Redis Cloud | Celery broker + job queue | app.redislabs.com |
| Cloudflare R2 | Video + thumbnail storage | dash.cloudflare.com |
| AWS (Polly) | Text-to-speech | console.aws.amazon.com |
| Nebius | nemotron text generation (script + visual bible) | studio.nebius.ai |
| Replicate | Flux-Schnell image generation | replicate.com |
| OpenAI | (ping only in Watchman) | platform.openai.com |
| Vercel | Frontend hosting | vercel.com |
| Railway | Backend hosting (prod) | railway.app |

---

## Branch info
- `main` — production
- `agentic_enhancement` — current working branch
