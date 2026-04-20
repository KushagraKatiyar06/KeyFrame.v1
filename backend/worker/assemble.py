# FFmpeg will be used to process the audio and images to connect it tg
import os
import subprocess
import tempfile

def _ffmpeg():
    return os.getenv('FFMPEG_PATH') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe')
    )

# use images and audio files to stitch into one video
def stitch_video(image_paths, audio_path, timings, job_id, temp_dir):

    os.makedirs(temp_dir, exist_ok=True)
    output_path = os.path.join(temp_dir, f'final_video{job_id}.mp4')

    print(f"Stitching video with {len(image_paths)} images and audio...\n\n")

    FFMPEG_PATH = _ffmpeg()

    # Step 1: create a silent MP4 segment per slide (one image at a time — low memory)
    segment_paths = []
    for i, (image_path, duration) in enumerate(zip(image_paths, timings)):
        segment_path = os.path.join(temp_dir, f'segment_{i}.mp4')
        cmd = [
            FFMPEG_PATH, '-y',
            '-loop', '1', '-framerate', '30', '-t', str(duration), '-i', image_path,
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
            '-pix_fmt', 'yuv420p', '-r', '30',
            '-an',
            segment_path
        ]
        print(f"1.{i+1}. Encoding segment {i+1}/{len(image_paths)}...")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise Exception(f"FFmpeg segment {i+1} failed: {result.stderr[-500:]}")
        segment_paths.append(segment_path)

    # Step 2: write concat list
    concat_list_path = os.path.join(temp_dir, 'concat_list.txt')
    with open(concat_list_path, 'w') as f:
        for seg in segment_paths:
            f.write(f"file '{seg}'\n")

    # Step 3: concat segments + mux audio
    print(f"2. Concatenating {len(segment_paths)} segments + audio...")
    cmd = [
        FFMPEG_PATH, '-y',
        '-f', 'concat', '-safe', '0', '-i', concat_list_path,
        '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        '-shortest',
        output_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg concat failed: {result.stderr[-500:]}")

    print(f"3. FFmpeg completed successfully")

    if not os.path.exists(output_path):
        raise Exception("FFmpeg completed but output file was not created")

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Video created: {output_path} ({file_size_mb:.2f} MB)")

    return output_path


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
