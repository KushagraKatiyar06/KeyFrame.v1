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
    style = job_data['style']

    session_seed = random.randint(1, 2147483647)
    temp_dir = os.path.join(tempfile.gettempdir(), f'keyframe_job_{job_id}')
    os.makedirs(temp_dir, exist_ok=True)
    print(f"Created job temp directory: {temp_dir}")

    try:
        # --- The Watchman: verify environment before spending any API credits ---
        database.update_job_status(job_id, 'agent_watchman_active')
        print(f"Starting job {job_id} - Style: {style}")
        watchman.preflight(job_id)

        # --- The Director: script + global visual bible ---
        database.update_job_status(job_id, 'agent_director_writing')
        print(f"Job {job_id}: Generating script...")
        script_data = script.generate_script(prompt, style)
        visual_bible = script.generate_visual_bible(script_data, style)
        script_data['visual_bible'] = visual_bible

        # --- The Continuity Artist + Voice Over in parallel ---
        database.update_job_status(job_id, 'agent_artist_slide_1')
        print(f"Job {job_id}: Generating images and voiceover in parallel...")

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
        print(f"Job {job_id}: Parallel generation complete!")

        # --- The Auditor: validate outputs, retry up to MAX_RETRIES ---
        database.update_job_status(job_id, 'agent_auditor_checking')
        print(f"Job {job_id}: Auditor checking outputs...")

        failed_images = auditor.validate_images(image_paths)
        for attempt in range(1, MAX_RETRIES):
            if not failed_images:
                break
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
            print(f"Auditor: audio retry {attempt}/{MAX_RETRIES - 1}...")
            database.update_job_status(job_id, 'agent_auditor_retry')
            audio_path, measured_timings = voice_over.generate_voice_over(script_data, job_id, temp_dir, style)
            script_data['timings'] = measured_timings
            audio_valid = auditor.validate_audio(audio_path)

        if not audio_valid:
            raise Exception(f"Audio failed validation after {MAX_RETRIES} attempts")

        # --- Assemble ---
        database.update_job_status(job_id, 'agent_stitching')
        print(f"Job {job_id}: Assembling video...")
        video_path = assemble.stitch_video(image_paths, audio_path, script_data['timings'], job_id, temp_dir)

        if not auditor.validate_video(video_path):
            raise Exception("Final video failed auditor validation")

        # clean up temp segments only after auditor confirms the final video is valid
        for f in os.listdir(temp_dir):
            if f.startswith('segment_') and f.endswith('.mp4'):
                os.remove(os.path.join(temp_dir, f))
        print("Auditor: temporary segments cleaned up")

        # --- Upload ---
        database.update_job_status(job_id, 'agent_uploading')
        print(f"Job {job_id}: Uploading to Cloudflare R2...")
        video_url, thumbnail_url = storage.upload_files(job_id, video_path, temp_dir)

        # --- Complete ---
        database.update_job_completed(job_id, video_url, thumbnail_url)
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
        database.update_job_status(job_id, 'failed')
        raise e
