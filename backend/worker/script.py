import os
import json
from openai import OpenAI

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
GPT_MODEL = "gpt-4o-mini"

AVAILABLE_VOICES = ['Ruth', 'Matthew', 'Brian', 'Amy', 'Joanna', 'Danielle']
VALID_CONTENT_TYPES = {'educational', 'narrative', 'humorous', 'general'}


def _extract_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON."""
    text = raw.strip()
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return json.loads(text.strip())


def _to_str(val) -> str:
    """Coerce any GPT value to a plain string (handles nested dicts/lists)."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # GPT sometimes wraps in {"description": "..."} — take first string value
        for v in val.values():
            result = _to_str(v)
            if result:
                return result
        return ''
    if isinstance(val, list):
        return ', '.join(_to_str(v) for v in val if v)
    if val is None:
        return ''
    return str(val)


#the main script generation method — style is now auto-detected from the prompt
def generate_script(prompt, style=None):
    print("Beginning script generation...\n\n")

    system_prompt = f"""You are a viral content creator specializing in short-form video. Analyze the prompt and create a complete, engaging video script targeting 60–75 seconds total runtime.

First, decide:
1. content_type: "educational" (facts/concepts), "narrative" (story-driven), "humorous" (meme/comedy), or "general"
2. slide_count — follow these rules strictly:
   - "narrative": 10–12 slides
   - "educational": 10–11 slides
   - "humorous": 10 slides
   - "general": 10 slides
   MINIMUM is always 10 slides. Never generate fewer than 10.
3. Voice casting from: {AVAILABLE_VOICES}
   - Assign 1 voice for pure narration/monologue
   - Assign multiple distinct voices if the content has characters, dialogue, or distinct personas
   - Match voice tone to role (e.g. Brian = authoritative UK narrator, Ruth = warm educator, Matthew = casual American)

For each slide assign:
- narration_prompt: exact spoken text (natural, conversational, flows well aloud)
  CRITICAL: Each narration MUST be 13–17 words. No exceptions.
  Target 5–7 seconds of spoken audio per slide at natural speech pace.
  Every word counts — make them punchy and impactful.
- image_prompt: extremely detailed visual description (subject, setting, lighting, mood, composition, art style, colors)
- duration: integer — estimated seconds from narration length (~2.5 words per second at natural speech pace)
- voice_id: one of {AVAILABLE_VOICES} — the voice that speaks this slide
- context_refs: list of 0-based integer slide indices whose visuals this slide directly builds on (e.g. [0]). Use [] if visually independent.

IMAGE PROMPT GUIDELINES:
- Be extremely specific: include subject, setting, lighting, mood, composition, art style
- No text in images — describe scenes only
- Each image should be visually distinct and striking
- Good: "A lone astronaut floating in deep space, Earth glowing below, cinematic wide shot, cool blue tones, photorealistic"
- Bad: "An astronaut in space"

NARRATION GUIDELINES:
- 18–25 words per slide — detailed, punchy, easy to follow when heard aloud
- Conversational, never robotic
- Natural transitions between slides
- Total target: 130–170 words across all slides
- This produces 55–70 seconds of audio at natural speech pace

Return JSON matching this schema exactly:
{{
  "title": "Engaging Video Title",
  "content_type": "educational|narrative|humorous|general",
  "slides": [
    {{
      "narration_prompt": "Natural spoken text for this slide",
      "image_prompt": "Extremely detailed visual description for AI image generation",
      "duration": 10,
      "voice_id": "Ruth",
      "context_refs": []
    }}
  ]
}}"""

    try:
        MIN_SLIDES = 10
        script_json = None

        for attempt in range(1, 4):
            print(f"1. Calling GPT (attempt {attempt}/3)...")
            user_msg = f"Create a video about: {prompt}"
            if attempt > 1:
                user_msg += f" IMPORTANT: You must generate exactly {MIN_SLIDES} slides minimum. Previous attempt had too few slides."

            response = openai_client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=4000,
                timeout=90
            )

            print("2. Parsing output...")
            raw_content = response.choices[0].message.content
            if not raw_content:
                print(f"Empty content from model on attempt {attempt}, retrying...")
                if attempt == 3:
                    raise ValueError("Model returned empty content after 3 attempts")
                continue

            script_json = _extract_json(raw_content)
            slide_count = len(script_json.get('slides', []))

            if slide_count >= MIN_SLIDES:
                print(f"3. Got {slide_count} slides — OK\n")
                break
            else:
                print(f"3. Got {slide_count} slides — need {MIN_SLIDES}, retrying...\n")
                if attempt == 3:
                    raise ValueError(f'Expected at least {MIN_SLIDES} slides, got {slide_count} after 3 attempts')

        print("3. Validating and normalising output\n")

        slides = script_json.get('slides', [])

        for i, slide in enumerate(slides):
            # coerce required string fields
            narration = _to_str(slide.get('narration_prompt', ''))
            if not narration:
                raise ValueError(f"Slide {i+1} missing narration_prompt")
            slide['narration_prompt'] = narration

            image_prompt = _to_str(slide.get('image_prompt', ''))
            if not image_prompt:
                raise ValueError(f"Slide {i+1} missing image_prompt")
            slide['image_prompt'] = image_prompt

            # coerce duration to int
            try:
                slide['duration'] = int(float(slide.get('duration') or 8))
            except (TypeError, ValueError):
                slide['duration'] = 8

            # validate voice_id
            if not slide.get('voice_id') or slide['voice_id'] not in AVAILABLE_VOICES:
                slide['voice_id'] = 'Matthew'

            # validate context_refs — integers only, back-references only
            raw_refs = slide.get('context_refs', [])
            coerced = []
            for r in raw_refs:
                try:
                    idx = int(r)
                    if 0 <= idx < i:
                        coerced.append(idx)
                except (TypeError, ValueError):
                    pass
            slide['context_refs'] = coerced

        # validate content_type
        if script_json.get('content_type') not in VALID_CONTENT_TYPES:
            script_json['content_type'] = 'general'

        timings = [slide['duration'] for slide in slides]
        script_json['timings'] = timings
        total_duration = sum(timings)

        print("4. Script generation complete: \n")
        print(f"Title: {script_json['title']}")
        print(f"Content type: {script_json.get('content_type', 'general')}")
        print(f"Total slides: {len(slides)}")
        print(f"Voices used: {list(set(s['voice_id'] for s in slides))}")
        print(f"Total duration: {total_duration} seconds\n")

        return script_json

    except json.JSONDecodeError as e:
        print(f"Error parsing GPT response as JSON: {e}")
        raise Exception("Failed to generate valid JSON")

    except Exception as e:
        print(f"Error generating script {e}")
        raise


def generate_visual_bible(script_data, style=None):
    """Generates a global visual consistency guide for image generation."""
    print("Director: generating visual bible...")

    title = script_data.get('title', '')
    content_type = script_data.get('content_type', 'general')
    prompts_summary = ' | '.join([s.get('image_prompt', '')[:80] for s in script_data.get('slides', [])])

    bible_prompt = f"""For a {content_type} video titled "{title}", create a concise Visual Bible to keep AI-generated images visually consistent.

Slide themes: {prompts_summary}

Return JSON with these four string fields:
{{
  "characters": "Key subjects/characters with consistent visual traits (appearance, clothing, style)",
  "color_palette": "3-5 dominant colors and their role (e.g. warm amber highlights, deep navy backgrounds)",
  "lighting_style": "Consistent lighting description (e.g. soft natural daylight, dramatic rim lighting)",
  "art_style": "Overall visual style (e.g. cinematic photography, flat illustration, vibrant cartoon)"
}}"""

    try:
        response = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{"role": "user", "content": bible_prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=400,
            timeout=30
        )

        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("Empty content from model")

        visual_bible = _extract_json(raw)

        # Normalise every field to a plain string regardless of what GPT returned
        for key in ('characters', 'color_palette', 'lighting_style', 'art_style'):
            visual_bible[key] = _to_str(visual_bible.get(key))

        print(f"Director: visual bible created — art style: {visual_bible.get('art_style', 'N/A')}")
        return visual_bible

    except Exception as e:
        print(f"Director: visual bible generation failed ({e}), continuing without it")
        return {}
