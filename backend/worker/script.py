import os
import json
from openai import OpenAI

chatgpt = OpenAI(api_key = os.getenv('OPENAI_API_KEY'))

AVAILABLE_VOICES = ['Ruth', 'Matthew', 'Brian', 'Amy', 'Joanna', 'Danielle']

#the main script generation method — style is now auto-detected from the prompt
def generate_script(prompt, style=None):
    print("Beginning script generation...\n\n")

    chatgpt_prompt = f"""You are a viral content creator specializing in short-form video. Analyze the prompt and create a complete, engaging video script.

First, decide:
1. content_type: "educational" (facts/concepts), "narrative" (story-driven), "humorous" (meme/comedy), or "general"
2. slide_count — follow these rules strictly:
   - "narrative": 12–16 slides (stories need space and structure)
   - "educational": 10–14 slides
   - "humorous": 10–13 slides
   - "general": 10–13 slides
   MINIMUM is always 10 slides. Never generate fewer than 10.
3. Voice casting from: {AVAILABLE_VOICES}
   - Assign 1 voice for pure narration/monologue
   - Assign multiple distinct voices if the content has characters, dialogue, or distinct personas
   - Match voice tone to role (e.g. Brian = authoritative UK narrator, Ruth = warm educator, Matthew = casual American)

For each slide assign:
- narration_prompt: exact spoken text (natural, conversational, flows well aloud)
  CRITICAL: Each narration MUST be 35–50 words. For narrative, 40–55 words.
  Keep each slide tight and punchy — the higher slide count carries the depth.
- image_prompt: extremely detailed visual description (subject, setting, lighting, mood, composition, art style, colors)
- duration: estimated seconds from narration length (~1 second per 2.3 words at fast-speech pace)
- voice_id: one of {AVAILABLE_VOICES} — the voice that speaks this slide
- context_refs: list of 0-based slide indices whose visuals this slide directly builds on (e.g. a character from slide 0 reappears in slide 4 → [0]). Use [] if visually independent.

IMAGE PROMPT GUIDELINES:
- Be extremely specific: include subject, setting, lighting, mood, composition, art style
- No text in images — describe scenes only
- Each image should be visually distinct and striking
- Good: "A lone astronaut floating in deep space, Earth glowing below, cinematic wide shot, cool blue tones, photorealistic"
- Bad: "An astronaut in space"

NARRATION GUIDELINES:
- 35–55 words per slide — tight, punchy, easy to follow when heard aloud
- Conversational, never robotic
- Natural transitions between slides
- Total target: 450–700 words for narrative, 350–550 for others

Return ONLY valid JSON in this exact format:
{{
  "title": "Engaging Video Title",
  "content_type": "educational|narrative|humorous|general",
  "slides": [
    {{
      "narration_prompt": "Natural spoken text for this slide",
      "image_prompt": "Extremely detailed visual description for AI image generation",
      "duration": 18,
      "voice_id": "Ruth",
      "context_refs": []
    }}
  ]
}}"""

    try:
        MIN_SLIDES = 10
        script_json = None

        for attempt in range(1, 4):
            print(f"1. Calling OpenAI (attempt {attempt}/3)...")
            user_msg = f"Create a video about: {prompt}"
            if attempt > 1:
                user_msg += f" IMPORTANT: You must generate exactly {MIN_SLIDES} slides minimum. Previous attempt had too few slides."

            response = chatgpt.chat.completions.create(
                model = "gpt-4o-mini",
                messages = [
                    {"role": "system", "content" : chatgpt_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature = 0.8,
                max_tokens = 4000,
                timeout = 90
            )

            print("2. Cleaning output...")
            output_json_string = response.choices[0].message.content.strip()

            if output_json_string.startswith('```json'):
                output_json_string = output_json_string[7:]
            if output_json_string.startswith('```'):
                output_json_string = output_json_string[3:]
            if output_json_string.endswith('```'):
                output_json_string = output_json_string[:-3]

            script_json = json.loads(output_json_string.strip())
            slide_count = len(script_json.get('slides', []))

            if slide_count >= MIN_SLIDES:
                print(f"3. Got {slide_count} slides — OK\n")
                break
            else:
                print(f"3. Got {slide_count} slides — need {MIN_SLIDES}, retrying...\n")
                if attempt == 3:
                    raise ValueError(f'Expected at least {MIN_SLIDES} slides, got {slide_count} after 3 attempts')

        #validates the json
        print("3. Validating Json output\n")

        slides = script_json.get('slides', [])

        for i, slide in enumerate(slides):
            if not slide.get('narration_prompt'):
                raise ValueError(f"Slide {i+1} missing narration_prompt")
            if not slide.get('image_prompt'):
                raise ValueError(f"Slide {i+1} missing image_prompt")
            if not slide.get('duration'):
                slide['duration'] = 8
            # validate voice_id
            if not slide.get('voice_id') or slide['voice_id'] not in AVAILABLE_VOICES:
                slide['voice_id'] = 'Matthew'
            # validate context_refs — only allow refs to previous slides
            raw_refs = slide.get('context_refs', [])
            slide['context_refs'] = [r for r in raw_refs if isinstance(r, int) and 0 <= r < i]

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
        print(f"Error parsing OpenAI response as JSON: {e}")
        print(f"Response was: {output_json_string}")
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

Return ONLY valid JSON:
{{
  "characters": "Key subjects/characters with consistent visual traits (appearance, clothing, style)",
  "color_palette": "3-5 dominant colors and their role (e.g. warm amber highlights, deep navy backgrounds)",
  "lighting_style": "Consistent lighting description (e.g. soft natural daylight, dramatic rim lighting)",
  "art_style": "Overall visual style (e.g. cinematic photography, flat illustration, vibrant cartoon)"
}}"""

    try:
        response = chatgpt.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": bible_prompt}],
            temperature=0.7,
            max_tokens=400,
            timeout=30
        )

        output = response.choices[0].message.content.strip()

        if output.startswith('```json'):
            output = output[7:]
        if output.startswith('```'):
            output = output[3:]
        if output.endswith('```'):
            output = output[:-3]

        visual_bible = json.loads(output.strip())
        print(f"Director: visual bible created — art style: {visual_bible.get('art_style', 'N/A')}")
        return visual_bible

    except Exception as e:
        print(f"Director: visual bible generation failed ({e}), continuing without it")
        return {}
