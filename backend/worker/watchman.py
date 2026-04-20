import os
import boto3
from openai import OpenAI

def preflight(job_id):
    print(f"Watchman: starting pre-flight checks for job {job_id}...")
    _check_ffmpeg()
    _ping_openai()
    _ping_nebius_text()
    _ping_replicate()
    _ping_aws()
    print("Watchman: all pre-flight checks passed.\n")

def _check_ffmpeg():
    import shutil
    import subprocess
    FFMPEG_PATH = os.getenv('FFMPEG_PATH') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe')
    )
    # if it's a plain command name (not a path), check PATH
    if not os.path.isabs(FFMPEG_PATH) and not os.path.exists(FFMPEG_PATH):
        if shutil.which(FFMPEG_PATH) is None:
            raise Exception(f"Watchman: FFmpeg not found at {FFMPEG_PATH}")
    elif os.path.isabs(FFMPEG_PATH) and not os.path.exists(FFMPEG_PATH):
        raise Exception(f"Watchman: FFmpeg not found at {FFMPEG_PATH}")
    print(f"Watchman: FFmpeg verified at {FFMPEG_PATH}")

def _ping_openai():
    try:
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        client.models.list()
        print("Watchman: OpenAI OK")
    except Exception as e:
        if _is_auth_error(e):
            raise Exception(f"Watchman: OpenAI auth failed — {e}")
        print(f"Watchman: OpenAI non-auth warning (continuing): {e}")

def _ping_nebius_text():
    try:
        client = OpenAI(
            base_url="https://api.tokenfactory.us-central1.nebius.com/v1/",
            api_key=os.getenv('NEBIUS_API_KEY')
        )
        client.models.list()
        print("Watchman: Nebius (text) OK")
    except Exception as e:
        if _is_auth_error(e):
            raise Exception(f"Watchman: Nebius auth failed — {e}")
        print(f"Watchman: Nebius non-auth warning (continuing): {e}")

def _ping_replicate():
    import httpx
    token = os.getenv('REPLICATE_API_TOKEN')
    if not token:
        raise Exception("Watchman: REPLICATE_API_TOKEN not set")
    try:
        r = httpx.get(
            "https://api.replicate.com/v1/account",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code in (401, 403):
            raise Exception(f"HTTP {r.status_code}")
        print("Watchman: Replicate OK")
    except Exception as e:
        if _is_auth_error(e):
            raise Exception(f"Watchman: Replicate auth failed — {e}")
        print(f"Watchman: Replicate non-auth warning (continuing): {e}")

def _ping_aws():
    try:
        polly = boto3.client(
            'polly',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        polly.describe_voices(LanguageCode='en-US')
        print("Watchman: AWS Polly OK")
    except Exception as e:
        if _is_auth_error(e):
            raise Exception(f"Watchman: AWS auth failed — {e}")
        print(f"Watchman: AWS non-auth warning (continuing): {e}")

def _is_auth_error(e):
    signals = ['401', '403', 'incorrect api key', 'authenticationerror',
               'invalidclienttokenid', 'authfailure', 'unrecognizedclientexception',
               'invalid_api_key', 'authentication']
    error_str = str(e).lower()
    return any(s in error_str for s in signals)
