import os
import time
import base64
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

BATCH_SIZE = 3
def generate_images(script_json, job_id, style=None, temp_dir=None, session_seed=None, status_callback=None):
    slides = script_json.get('slides', [])
    visual_bible = script_json.get('visual_bible', {})
    content_type = script_json.get('content_type', 'general')

    bible_parts = []
    if visual_bible.get('art_style'):
        bible_parts.append(visual_bible['art_style'])
    if visual_bible.get('color_palette'):
        bible_parts.append(f"color palette: {visual_bible['color_palette']}")
    if visual_bible.get('lighting_style'):
        bible_parts.append(f"lighting: {visual_bible['lighting_style']}")
    bible_prefix = (', '.join(bible_parts) + '. ') if bible_parts else ''

    image_prompts = []
    for i, slide in enumerate(slides):
        base_prompt = slide.get('image_prompt', '')
        context_refs = slide.get('context_refs', [])

        context_parts = []
        if context_refs:
            for ref_idx in context_refs:
                if ref_idx < len(slides) and ref_idx < i:
                    context_parts.append(slides[ref_idx]['image_prompt'][:80])
        elif i > 0:
            context_parts.append(slides[i - 1]['image_prompt'][:60])

        if context_parts:
            context_str = ' | '.join(context_parts)
            image_prompts.append(f"{bible_prefix}{base_prompt}. Visual continuity from: {context_str}")
        else:
            image_prompts.append(f"{bible_prefix}{base_prompt}")

    print(f"Using Nebius (Flux-Schnell) for content_type={content_type}")
    client = OpenAI(
        base_url="https://api.studio.nebius.com/v1",
        api_key=os.getenv('NEBIUS_API_KEY'),
    )
    model = "black-forest-labs/flux-schnell"

    os.makedirs(temp_dir, exist_ok=True)
    image_paths = [None] * len(slides)

    def generate_single(i, prompt):
        for attempt in range(1, 4):
            try:
                completion = client.images.generate(
                    model=model,
                    prompt=prompt,
                    response_format="b64_json",
                    timeout=60,
                    extra_body={
                        "response_extension": "jpg",
                        "width": 1920,
                        "height": 1080,
                        "num_inference_steps": 4,
                        "seed": session_seed if session_seed is not None else -1
                    }
                )
                image_bytes = base64.b64decode(completion.data[0].b64_json)
                image_path = os.path.join(temp_dir, f'image_{i}.jpg')
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)
                print(f"Image {i+1}/{len(slides)} generated: {image_path}")
                return image_path
            except Exception as e:
                print(f"Image {i+1} attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(3)
        raise Exception(f"Image {i+1} failed after 3 attempts")

    print(f"Generating {len(slides)} images in batches of {BATCH_SIZE}...")

    for batch_start in range(0, len(slides), BATCH_SIZE):
        batch_indices = list(range(batch_start, min(batch_start + BATCH_SIZE, len(slides))))
        batch_nums = [str(i + 1) for i in batch_indices]

        if status_callback:
            status_callback(f'agent_artist_slides_{",".join(batch_nums)}')

        print(f"Batch: slides {batch_nums}")

        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = [executor.submit(generate_single, i, image_prompts[i]) for i in batch_indices]


        for future, i in zip(futures, batch_indices):
            image_paths[i] = future.result()  # re-raises on failure

    print(f"All {len(image_paths)} images generated successfully")
    return image_paths
