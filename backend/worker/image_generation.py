import os
import time
import replicate
from concurrent.futures import ThreadPoolExecutor

BATCH_SIZE = 1
def generate_images(script_json, job_id, style=None, temp_dir=None, session_seed=None, status_callback=None):
    slides = script_json.get('slides', [])
    visual_bible = script_json.get('visual_bible', {})
    content_type = script_json.get('content_type', 'general')

    bible_parts = []
    if visual_bible.get('art_style'):
        bible_parts.append(str(visual_bible['art_style']))
    if visual_bible.get('color_palette'):
        bible_parts.append(f"color palette: {visual_bible['color_palette']}")
    if visual_bible.get('lighting_style'):
        bible_parts.append(f"lighting: {visual_bible['lighting_style']}")
    bible_prefix = (', '.join(str(p) for p in bible_parts) + '. ') if bible_parts else ''

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

    print(f"Using Replicate (Flux-Schnell) for content_type={content_type}")

    os.makedirs(temp_dir, exist_ok=True)
    image_paths = [None] * len(slides)

    def generate_single(i, prompt):
        for attempt in range(1, 4):
            try:
                replicate_input = {
                    "prompt": prompt,
                    "num_outputs": 1,
                    "aspect_ratio": "16:9",
                    "output_format": "jpg",
                    "output_quality": 85,
                    "num_inference_steps": 4,
                }
                if session_seed is not None:
                    replicate_input["seed"] = session_seed

                output = replicate.run(
                    "black-forest-labs/flux-schnell",
                    input=replicate_input
                )
                image_bytes = output[0].read()
                image_path = os.path.join(temp_dir, f'image_{i}.jpg')
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)
                print(f"Image {i+1}/{len(slides)} generated: {image_path}")
                return image_path
            except Exception as e:
                err_str = str(e)
                print(f"Image {i+1} attempt {attempt}/3 failed: {err_str}")
                if attempt < 3:
                    wait = 15 if '429' in err_str else 3
                    time.sleep(wait)
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
