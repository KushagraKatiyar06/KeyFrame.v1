# FFmpeg will be used to process the audio and images to connect it tg
import os
import subprocess
import tempfile

# use images and audio files to stitch into one video
def stitch_video(image_paths, audio_path, timings, job_id, temp_dir):

    os.makedirs(temp_dir, exist_ok=True)
    output_path = os.path.join(temp_dir, f'final_video{job_id}.mp4')

    print(f"Stitching video with {len(image_paths)} images and audio...\n\n")

    try:
        FFMPEG_PATH = os.getenv('FFMPEG_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe'))

        n = len(image_paths)

        input_args = []
        for image_path, duration in zip(image_paths, timings):
            input_args += ['-framerate', '30', '-loop', '1', '-t', str(duration), '-i', image_path]
        input_args += ['-i', audio_path]

        scale_parts = ';'.join(
            f'[{i}:v]scale=1920:1080,setsar=1,setpts=PTS-STARTPTS[v{i}]' for i in range(n)
        )
        concat_inputs = ''.join(f'[v{i}]' for i in range(n))
        filter_complex = f'{scale_parts};{concat_inputs}concat=n={n}:v=1:a=0[outv]'

        ffmpeg_command = [
            FFMPEG_PATH,
            '-y',
            *input_args,
            '-filter_complex', filter_complex,
            '-map', '[outv]',
            '-map', f'{n}:a',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-pix_fmt', 'yuv420p',
            '-r', '30',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-shortest',
            output_path
        ]

        print(f"1. Running single-pass FFmpeg (filter_complex, {n} slides)...")
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        print(f"2. FFmpeg completed successfully")

        if not os.path.exists(output_path):
            raise Exception("FFmpeg completed but output file was not created")

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Video created: {output_path} ({file_size_mb:.2f} MB)")

        return output_path

    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr}")
        raise Exception(f"FFmpeg failed: {e.stderr}")
    except Exception as e:
        print(f"Error stitching video: {e}")
        raise

def get_video_info(video_path):
    try:
        FFPROBE_PATH = os.getenv('FFPROBE_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffprobe.exe'))
        command = [
            FFPROBE_PATH,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        import json
        info = json.loads(result.stdout)
        
        duration = float(info['format'].get('duration', 0))
        size_mb = int(info['format'].get('size', 0)) / (1024 * 1024)
        
        print(f"Video info: {duration:.2f}s duration, {size_mb:.2f} MB")
        return info
        
    except Exception as e:
        print(f"Could not get video info: {e}")
        return None