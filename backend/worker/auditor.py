import os

def validate_images(image_paths):
    """Returns list of failed indices (missing or 0-byte images)"""
    failed = []
    for i, path in enumerate(image_paths):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"Auditor: image {i+1} FAILED (missing or 0 bytes)")
            failed.append(i)
        else:
            print(f"Auditor: image {i+1} OK ({os.path.getsize(path)} bytes)")
    return failed

def validate_audio(audio_path):
    """Returns True if audio exists and duration > 0.5s"""
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        print(f"Auditor: audio FAILED (missing or 0 bytes)")
        return False
    try:
        from mutagen.mp3 import MP3
        duration = MP3(audio_path).info.length
        if duration > 0.5:
            print(f"Auditor: audio OK ({duration:.2f}s)")
            return True
        print(f"Auditor: audio FAILED (duration {duration:.2f}s < 0.5s)")
        return False
    except Exception as e:
        print(f"Auditor: audio validation error — {e}")
        return False

def validate_video(video_path):
    """Returns True if final video exists and is > 0 bytes"""
    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        print(f"Auditor: final video FAILED")
        return False
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"Auditor: final video OK ({size_mb:.2f} MB)")
    return True
