#This will run the full ai pipeline
import os
import random
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import database
import script
import image_generation
import voice_over
import assemble
import storage
import watchman
import auditor
from app import app

#load environment variables for utility functions
load_dotenv()

MAX_RETRIES = 3

@app.task(bind=True)
def process_video_job(self, job_data):
    """
    Main task that processes a video generation job
    Takes job_data dict with: { id, prompt, style }
    """
    job_id = job_data['id']
    prompt = job_data['prompt']
    style = job_data.get('style', 'Default')

    session_seed = random.randint(1, 2147483647)
    temp_dir = os.path.join(tempfile.gettempdir(), f'keyframe_job_{job_id}')
    os.makedirs(temp_dir, exist_ok=True)
    print(f"Created job temp directory: {temp_dir}")

    try:
        # --- The Watchman: verify environment before spending any API credits ---
        database.update_job_status(job_id, 'agent_watchman_active')
        database.append_job_log(job_id, 'Watchman: starting pre-flight checks...')
        print(f"Starting job {job_id}")
        watchman.preflight(job_id)
        database.append_job_log(job_id, 'Watchman: all services reachable. Environment OK.')

        # --- The Director: script + global visual bible ---
        database.update_job_status(job_id, 'agent_director_writing')
        database.append_job_log(job_id, f'Director: generating script for style="{style}"...')
        print(f"Job {job_id}: Generating script...")
        script_data = script.generate_script(prompt, style)
        database.append_job_log(job_id, f'Director: script ready — {len(script_data.get("slides", []))} slides, content_type={script_data.get("content_type","general")}')
        database.append_job_log(job_id, 'Director: generating Visual Bible (art style + color palette)...')
        visual_bible = script.generate_visual_bible(script_data, style)
        script_data['visual_bible'] = visual_bible
        database.append_job_log(job_id, 'Director: Visual Bible complete.')

        # Signal slide count + context_refs to the frontend for per-slide agent visualization
        slide_count = len(script_data.get('slides', []))
        refs_pairs = []
        for i, slide in enumerate(script_data['slides']):
            for ref in slide.get('context_refs', []):
                refs_pairs.append(f'{i}>{ref}')
        refs_part = ':' + ','.join(refs_pairs) if refs_pairs else ''
        database.update_job_status(job_id, f'agent_director_slides_{slide_count}{refs_part}')
        print(f"Job {job_id}: Director done — {slide_count} slides, refs={refs_pairs}, content_type={script_data.get('content_type','general')}")

        # --- The Continuity Artist + Voice Over in parallel ---
        # Images are generated sequentially (per-slide agent) while voice runs in parallel
        database.append_job_log(job_id, f'Continuity Artist: generating {slide_count} images in batches of 3 (seed={session_seed})...')
        database.append_job_log(job_id, 'Voice Over: starting TTS generation in parallel...')
        print(f"Job {job_id}: Starting images (sequential) + voiceover (parallel)...")

        def generate_images_task():
            return image_generation.generate_images(
                script_data, job_id, style, temp_dir, session_seed,
                status_callback=lambda s: database.update_job_status(job_id, s)
            )

        def generate_voiceover_task():
            return voice_over.generate_voice_over(script_data, job_id, temp_dir, style)

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_images = executor.submit(generate_images_task)
            future_voice = executor.submit(generate_voiceover_task)
            image_paths = future_images.result()
            audio_path, measured_timings = future_voice.result()

        script_data['timings'] = measured_timings
        database.append_job_log(job_id, f'Continuity Artist: all {slide_count} images generated.')
        database.append_job_log(job_id, 'Voice Over: audio complete.')
        print(f"Job {job_id}: Parallel generation complete!")

        # --- The Auditor: validate outputs, retry up to MAX_RETRIES ---
        database.update_job_status(job_id, 'agent_auditor_checking')
        database.append_job_log(job_id, 'Auditor: validating images and audio...')
        print(f"Job {job_id}: Auditor checking outputs...")

        failed_images = auditor.validate_images(image_paths)
        for attempt in range(1, MAX_RETRIES):
            if not failed_images:
                break
            database.append_job_log(job_id, f'Auditor: image validation failed (slides {failed_images}), retry {attempt}/{MAX_RETRIES - 1}...')
            print(f"Auditor: image retry {attempt}/{MAX_RETRIES - 1}...")
            database.update_job_status(job_id, 'agent_auditor_retry')
            image_paths = image_generation.generate_images(script_data, job_id, style, temp_dir, session_seed)
            failed_images = auditor.validate_images(image_paths)

        if failed_images:
            raise Exception(f"Images failed validation after {MAX_RETRIES} attempts: slides {failed_images}")

        audio_valid = auditor.validate_audio(audio_path)
        for attempt in range(1, MAX_RETRIES):
            if audio_valid:
                break
            database.append_job_log(job_id, f'Auditor: audio validation failed, retry {attempt}/{MAX_RETRIES - 1}...')
            print(f"Auditor: audio retry {attempt}/{MAX_RETRIES - 1}...")
            database.update_job_status(job_id, 'agent_auditor_retry')
            audio_path, measured_timings = voice_over.generate_voice_over(script_data, job_id, temp_dir, style)
            script_data['timings'] = measured_timings
            audio_valid = auditor.validate_audio(audio_path)

        if not audio_valid:
            raise Exception(f"Audio failed validation after {MAX_RETRIES} attempts")

        database.append_job_log(job_id, 'Auditor: all outputs valid.')

        # --- Assemble ---
        database.update_job_status(job_id, 'agent_stitching')
        database.append_job_log(job_id, f'Editor: stitching {slide_count} segments with FFmpeg...')
        print(f"Job {job_id}: Assembling video...")
        video_path = assemble.stitch_video(image_paths, audio_path, script_data['timings'], job_id, temp_dir)

        if not auditor.validate_video(video_path):
            raise Exception("Final video failed auditor validation")

        # clean up temp segments only after auditor confirms the final video is valid
        for f in os.listdir(temp_dir):
            if f.startswith('segment_') and f.endswith('.mp4'):
                os.remove(os.path.join(temp_dir, f))
        database.append_job_log(job_id, 'Editor: video assembled and validated. Temp segments cleaned.')
        print("Auditor: temporary segments cleaned up")

        # --- Upload ---
        database.update_job_status(job_id, 'agent_uploading')
        database.append_job_log(job_id, 'Uploading video and thumbnail to Cloudflare R2...')
        print(f"Job {job_id}: Uploading to Cloudflare R2...")
        video_url, thumbnail_url = storage.upload_files(job_id, video_path, temp_dir)

        # --- Complete ---
        database.update_job_completed(job_id, video_url, thumbnail_url)
        database.append_job_log(job_id, f'Done! Video available at: {video_url}')
        print(f"Job {job_id} completed successfully!")

        try:
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            print(f"Warning: could not clean up temp dir: {e}")

        return {
            'status': 'success',
            'job_id': job_id,
            'video_url': video_url,
            'thumbnail_url': thumbnail_url
        }

    except Exception as e:
        print(f"Job {job_id} failed with error: {str(e)}")
        database.append_job_log(job_id, f'FAILED: {str(e)}')
        database.update_job_status(job_id, 'failed')
        raise e
