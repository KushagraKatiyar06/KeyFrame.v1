import os
import boto3
from openai import OpenAI

def preflight(job_id):
    print(f"Watchman: starting pre-flight checks for job {job_id}...")
    _check_ffmpeg()
    _ping_openai()
    _ping_nebius()
    _ping_aws()
    print("Watchman: all pre-flight checks passed.\n")

def _check_ffmpeg():
    FFMPEG_PATH = os.getenv('FFMPEG_PATH') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'ffmpeg.exe')
    )
    if not os.path.exists(FFMPEG_PATH):
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

def _ping_nebius():
    try:
        client = OpenAI(
            base_url="https://api.studio.nebius.com/v1",
            api_key=os.getenv('NEBIUS_API_KEY')
        )
        client.models.list()
        print("Watchman: Nebius OK")
    except Exception as e:
        if _is_auth_error(e):
            raise Exception(f"Watchman: Nebius auth failed — {e}")
        print(f"Watchman: Nebius non-auth warning (continuing): {e}")

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
