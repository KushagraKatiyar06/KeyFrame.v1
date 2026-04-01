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

        segment_paths = []
        FFMPEG_PATH = os.getenv('FFMPEG_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe'))

        print("1. Iterating through clips and audios and stitching into video")

        for i, (image_path, duration) in enumerate(zip(image_paths, timings)):
            segment_path = os.path.join(temp_dir, f'segment_{i}.mp4')
            # -loop 1 keeps the image for the specified duration
            segment_cmd = [
                FFMPEG_PATH,
                '-y',
                '-loop', '1',
                '-i', image_path,
                '-c:v', 'libx264',
                '-t', str(duration),
                '-pix_fmt', 'yuv420p',
                '-vf', 'scale=1920:1080',
                '-r', '30',
                '-preset', 'medium',
                '-crf', '23',
                segment_path
            ]

            print(f"Encoding segment {i+1}/{len(image_paths)}: {segment_path} ({duration}s)")
            subprocess.run(segment_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if not os.path.exists(segment_path):
                raise Exception(f"Failed to create segment: {segment_path}")
            segment_paths.append(segment_path)

        concat_file_path = os.path.join(temp_dir, 'concat_list.txt')
        with open(concat_file_path, 'w', encoding='utf-8') as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")

        ffmpeg_command = [
            FFMPEG_PATH,
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file_path,
            '-i', audio_path,
            '-map', '0:v',
            '-map', '1:a',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-shortest',
            output_path
        ]

        print(f"2. Running FFmpeg concat + mux command...")
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        print(f"3. FFmpeg completed successfully")
        
        # verify the output file exists
        if not os.path.exists(output_path):
            raise Exception("FFmpeg completed but output file was not created")
        
        # get file size for logging
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