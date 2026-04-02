#This is where everything will be stored (the storage will follow a stack kind of approach. 
#Each topic will have 5 videos. When a new one is generated, the old one will disappear. 
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
import subprocess

# MODIFIED: Added temp_dir parameter
def upload_files(job_id, video_path, temp_dir):
    """Upload video and thumbnail to Cloudflare R2
    Returns (video_url, thumbnail_url)
    """
    
    # gets the cloudflare r2 credentials from environment
    account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    access_key_id = os.getenv('CLOUDFLARE_ACCESS_KEY_ID')
    secret_access_key = os.getenv('CLOUDFLARE_SECRET_ACCESS_KEY')
    bucket_name = os.getenv('R2_BUCKET_NAME')
    
    # construct the r2 endpoint url
    # format: https://<account_id>.r2.cloudflarestorage.com
    endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'
    
    # initializes s3 client for cloudflare r2
    # verify=False works around SSL handshake failures on Python 3.14
    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name='auto'
    )
    try:
        print(f"Uploading video to Cloudflare R2...")
        
        # generates unique filenames using job_id
        video_filename = f'videos/{job_id}.mp4'
        thumbnail_filename = f'thumbnails/{job_id}.jpg'
        
        # uploads the video file
        with open(video_path, 'rb') as video_file:
            s3_client.upload_fileobj(
                video_file,
                bucket_name,
                video_filename,
                ExtraArgs={
                    'ContentType':'video/mp4',
                    'ACL': 'public-read'  # makes it publicly accessible
                }
            )
        
        print(f"Video uploaded successfully: {video_filename}")
        
        # generates thumbnail from the video
        # MODIFIED: Pass temp_dir to generate_thumbnail
        thumbnail_path = generate_thumbnail(video_path, temp_dir, job_id) 
        # uploads the thumbnail
        with open(thumbnail_path, 'rb') as thumbnail_file:
            s3_client.upload_fileobj(
                thumbnail_file,
                bucket_name,
                thumbnail_filename,
                ExtraArgs={
                    'ContentType': 'image/jpeg',
                    'ACL': 'public-read'
                }
            )
        
        print(f"Thumbnail uploaded successfully: {thumbnail_filename}")
        
        # constructs the public urls
        # format: https://pub-xxxxx.r2.dev/filename
        # note: need to set up a public R2 domain in cloudflare dashboard
        public_domain = os.getenv('R2_PUBLIC_DOMAIN', f'{bucket_name}.r2.dev')
        
        video_url = f'https://{public_domain}/{video_filename}'
        thumbnail_url = f'https://{public_domain}/{thumbnail_filename}'
        
        print(f"Video URL: {video_url}")
        print(f"Thumbnail URL: {thumbnail_url}")
        
        return video_url, thumbnail_url
        
    except (BotoCoreError, ClientError) as error:
        print(f"Error uploading to R2: {error}")
        raise
    except Exception as e:
        print(f"Unexpected error during upload: {e}")
        raise

# MODIFIED: Removed job_id, added temp_dir
def generate_thumbnail(video_path, temp_dir, job_id):
    """Generate a thumbnail from the video using FFmpeg
    Takes a frame from 1 second into the video
    """
    
    # REMOVED: Internal temp_dir creation logic is now removed.
    # The output path uses the passed temp_dir.
    thumbnail_path = os.path.join(temp_dir, f'thumbnail{job_id}.jpg')
    
    try:
        # ffmpeg command to extract a frame at 1 second
        FFMPEG_PATH = os.getenv('FFMPEG_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe'))

        ffmpeg_command = [
            FFMPEG_PATH,
            '-y',  # overwrite if exists
            '-i', video_path,  # input video
            '-ss', '00:00:01',  # seek to 1 second
            '-vframes', '1',  # extract only 1 frame
            '-vf', 'scale=1280:720',  
            '-q:v', '2',  
            thumbnail_path
        ]
        
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        print(f"Thumbnail generated: {thumbnail_path}")
        return thumbnail_path
        
    except subprocess.CalledProcessError as e:
        print(f"Error generating thumbnail: {e.stderr}")
        raise Exception(f"Failed to generate thumbnail: {e.stderr}")
    except Exception as e:
        print(f"Unexpected error generating thumbnail: {e}")
        raise

# REMOVED: The entire delete_temp_files function is deleted 
# as cleanup is now centralized in orchestrator.py.