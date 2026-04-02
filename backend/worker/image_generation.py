import os
import time
import base64
from openai import OpenAI

# main image generation method — sequential per slide, smart context from context_refs
def generate_images(script_json, job_id, style=None, temp_dir=None, session_seed=None, status_callback=None):
    slides = script_json.get('slides', [])
    visual_bible = script_json.get('visual_bible', {})
    content_type = script_json.get('content_type', 'general')

    # build a prefix from the visual bible to prepend to every prompt
    bible_parts = []
    if visual_bible.get('art_style'):
        bible_parts.append(visual_bible['art_style'])
    if visual_bible.get('color_palette'):
        bible_parts.append(f"color palette: {visual_bible['color_palette']}")
    if visual_bible.get('lighting_style'):
        bible_parts.append(f"lighting: {visual_bible['lighting_style']}")
    bible_prefix = (', '.join(bible_parts) + '. ') if bible_parts else ''

    print(f"Beginning image generation...\n\n")

    # always use Nebius Flux-Schnell
    print(f"1. Using Nebius (Flux-Schnell) for content_type={content_type}\n")
    client = OpenAI(
        base_url="https://api.studio.nebius.com/v1",
        api_key=os.getenv('NEBIUS_API_KEY'),
    )
    model = "black-forest-labs/flux-schnell"
    use_dalle = False

    print("2. Generating images sequentially (per-slide agent)...")
    os.makedirs(temp_dir, exist_ok=True)

    image_paths = []

    for i, slide in enumerate(slides):
        if status_callback:
            status_callback(f'agent_artist_slide_{i+1}')

        base_prompt = slide.get('image_prompt', '')
        context_refs = slide.get('context_refs', [])

        # smart context: use context_refs if present, else fall back to previous slide
        context_parts = []
        if context_refs:
            for ref_idx in context_refs:
                if ref_idx < len(slides) and ref_idx < i:
                    context_parts.append(slides[ref_idx]['image_prompt'][:80])
            print(f"   Slide {i+1}: using context from slides {[r+1 for r in context_refs]}")
        elif i > 0:
            # default: light reference to the immediately preceding slide
            context_parts.append(slides[i-1]['image_prompt'][:60])

        if context_parts:
            context_str = ' | '.join(context_parts)
            image_prompt = f"{bible_prefix}{base_prompt}. Visual continuity from: {context_str}"
        else:
            image_prompt = f"{bible_prefix}{base_prompt}"

        success = False
        for attempt in range(1, 4):
            try:
                completion = client.images.generate(
                    model=model,
                    prompt=image_prompt,
                    response_format="b64_json",
                    timeout=60,
                    extra_body={
                        "response_extension": "jpg",
                        "width": 1920,
                        "height": 1080,
                        "num_inference_steps": 16,
                        "seed": session_seed if session_seed is not None else -1
                    }
                )
                image_bytes = base64.b64decode(completion.data[0].b64_json)

                image_path = os.path.join(temp_dir, f'image_{i}.jpg')
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)

                print(f"Image {i+1}/{len(slides)} generated: {image_path}")
                image_paths.append(image_path)
                success = True
                break

            except Exception as e:
                print(f"Image {i+1} attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(3)

        if not success:
            raise Exception(f"Image {i+1} failed after 3 attempts")

    print(f"All {len(image_paths)} images generated successfully")
    return image_paths
