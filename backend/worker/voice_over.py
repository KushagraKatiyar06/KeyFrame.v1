import os
import html
import tempfile
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import subprocess
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# main audio duration extraction
def get_audio_duration_mutagen(path):
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return audio.info.length
    except Exception:
        return None

# fallback audio duration extraction
def get_audio_duration_ffprobe(path):
    try:
        FFPROBE_PATH = os.getenv('FFPROBE_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffprobe.exe'))
        cmd = [
            FFPROBE_PATH, '-v', 'error', '-select_streams', 'a:0', '-show_entries',
            'stream=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return None

def get_audio_duration(path):
    result = get_audio_duration_mutagen(path)

    if result:
        return result
    else:
        result = get_audio_duration_ffprobe(path)
        if result:
            return result

    print("Error recieving audio duration.")
    return None

def _wrap_ssml(narration):
    """Wraps narration text in SSML with faster prosody rate."""
    safe = html.escape(narration)
    return f'<speak><prosody rate="120%">{safe}</prosody></speak>'

# main tts generation method — voice is now per-slide from script_json
def generate_voice_over(script_json, job_id, temp_dir, style=None):
    print("Beginning voice over generation...\n\n")

    polly = boto3.client(
        'polly',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        config=Config(connect_timeout=10, read_timeout=30)
    )

    slides = script_json.get('slides', [])

    print("1. Voice assignments per slide:")
    for i, slide in enumerate(slides):
        print(f"   Slide {i+1}: {slide.get('voice_id', 'Matthew')}")

    print("\n2. Generating all voiceovers in parallel (polly api calls)... \n")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        def generate_single_voiceover(i, slide):
            narration = slide.get('narration_prompt', '')
            voice_id = slide.get('voice_id', 'Matthew')
            ssml_text = _wrap_ssml(narration)

            print(f"{i+1}. Polly: narrating slide {i+1}/{len(slides)} with {voice_id} ({len(narration)} chars)")

            # try generative engine with SSML, fall back to neural, then plain text
            try:
                response = polly.synthesize_speech(
                    Text=ssml_text,
                    TextType='ssml',
                    OutputFormat='mp3',
                    VoiceId=voice_id,
                    Engine='generative'
                )
            except Exception:
                try:
                    response = polly.synthesize_speech(
                        Text=ssml_text,
                        TextType='ssml',
                        OutputFormat='mp3',
                        VoiceId=voice_id,
                        Engine='neural'
                    )
                except Exception:
                    # final fallback: plain text with neural
                    response = polly.synthesize_speech(
                        Text=narration,
                        TextType='text',
                        OutputFormat='mp3',
                        VoiceId=voice_id,
                        Engine='neural'
                    )

            audio_stream = response.get('AudioStream')
            if not audio_stream:
                raise Exception(f'No audio stream returned for slide {i}')

            slide_mp3 = os.path.join(temp_dir, f'slide_{i}.mp3')
            with open(slide_mp3, 'wb') as f:
                f.write(audio_stream.read())

            # measure duration
            duration = get_audio_duration(slide_mp3)
            if duration is None:
                raise Exception(f"Could not determine duration for {slide_mp3}")

            print(f"Slide {i+1} duration: {duration:.2f}s")
            return (i, slide_mp3, float(duration))

        # Execute voiceover generation in parallel
        voiceover_results = {}
        with ThreadPoolExecutor(max_workers=len(slides)) as executor:
            futures = {executor.submit(generate_single_voiceover, i, slide): i for i, slide in enumerate(slides)}

            for future in as_completed(futures):
                i, slide_mp3, duration = future.result()
                voiceover_results[i] = (slide_mp3, duration)

        # Sort by index to maintain order
        slide_paths = []
        slide_durations = []
        for i in sorted(voiceover_results.keys()):
            path, duration = voiceover_results[i]
            slide_paths.append(path)
            slide_durations.append(duration)

        # concatenate slide mp3s into one file using pure Python binary concat
        print("\n3. Concatenating slide mp3s into one...")

        full_audio = os.path.join(temp_dir, 'voiceover_full.mp3')

        print("Concatenating slide audio into full voiceover...")
        with open(full_audio, 'wb') as outfile:
            for p in slide_paths:
                with open(p, 'rb') as infile:
                    outfile.write(infile.read())

        # final sanity check
        print("4. Final tts checks...")

        if not os.path.exists(full_audio):
            raise Exception("Failed to create concatenated voiceover file")

        total = sum(slide_durations)
        print(f"Voiceover created: {full_audio} (total {total:.2f}s)")

        return full_audio, slide_durations

    except (BotoCoreError, ClientError) as e:
        print(f"Polly error: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error in voice_over: {e}")
        raise
