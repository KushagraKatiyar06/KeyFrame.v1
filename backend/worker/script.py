import os
import json
from openai import OpenAI

chatgpt = OpenAI(api_key = os.getenv('OPENAI_API_KEY'))

#the main script generation method
def generate_script(prompt, style):
    print("Beginning script generation...\n\n")

    #setting unique values for different style of videos
    image_count = {'Educational' : 6, 'Storytelling' : 10, 'Meme' : 10, 'Default' : 5}
    tts_count = {'Educational' : 6, 'Storytelling' : 10, 'Meme' : 10, 'Default' : 5}
    video_length = {'Educational' : 60, 'Storytelling' : 60, "Meme" : 30, 'Default' : 30}

    slide_length = {'Educational' : video_length['Educational'] / image_count['Educational'], 
                    'Storytelling' : video_length['Storytelling'] / image_count["Storytelling"], 
                    'Meme' : video_length['Meme'] / image_count['Meme'], 
                    'Default' : video_length['Default'] / image_count['Default']}
    
    narration_word_count = {'Educational' : '300-360', 'Storytelling' : '300-360', 'Meme' : '180-200', 'Default' : '180-200'}

    #overview of what each style should look like
    style_instructions = {
        'Educational' : """Script an educational video to briefly teach a concept. Use facts, explanations and real-world examples. If needed, break down complexities to parts.
        Each slide should build on the previous one logically but use simple language. Image prompts should show diagrams, illustrations, or visualizations.""",

        'Storytelling' : """Script a story with a clear beginning, middle, or end. Depending on the prompt, amplify the comedy, suspense or horror aspect. Use vivid descriptions and sensory details.
        Each slide should logically advance the plot. Image prompts should be very visual and capture the dialogue visually.""",

        'Meme' : """Script a funny and relevant funny video that takes inspiration from the latest tiktok and instagram trends. Depending on the prompt, make the video relatable and shareable. 
        use modern internet humor and trending formats and be playful/ironic where appropriate. Reference common experiences everyone understands and each slide should build to a punchline or funny
        moment. Image prompts should be visually comedic or exaggerated.""", 

        'Default' : f"""Create a basic video that follows the prompt"""
    }

    #ontext for chatgpt to correctly return json data for image/tts generation
    chatgpt_prompt = f"""You are viral content creator specializing in short form content. Generate a compelling, engaging script.
    style: {style}, style instructions: {style_instructions.get(style, style_instructions['Default'])}. Generate exactly {image_count.get(style, image_count['Default'])} image prompts and {tts_count.get(style, tts_count['Default'])} narration prompts.
    the overall word count for the entire script should be {narration_word_count.get(style, narration_word_count['Default'])}. Each slide has three components. 1. narration_prompt: the exact spoken text for this slide
    (conversational, natural, flows well when spoken aloud). 2. image_prompt: a highly detailed, visual description for AI image generation (be specific about composition, style, mood, colors, subjects)
    3. duration: Estimated time in seconds (will be adjusted based on actual audio length, target ~{slide_length.get(style, slide_length['Default']):.1f}s per slide)

    IMAGE PROMPT GUIDELINES:
    Be extremely specific and descriptive (include: subject, setting, lighting, mood, composition, art style)
    Good example: "A cozy coffee shop interior at sunrise, warm golden light streaming through large windows, a steaming 
    latte on a wooden table in the foreground, soft bokeh background with blurred customers, cinematic photography style, 
    warm color palette". Bad example: "A coffee shop". Avoid text in images - describe visual scenes only. Each image should 
    be distinct and visually interesting. Images should match and enhance the narration
    
    NARRATION PROMPT GUIDELINES:
    Write as if speaking directly to the viewer. Use short, punchy sentences that are easy to understand when heard. Make it conversational 
    and engaging, not robotic. Each narration should naturally flow into the next. Total word count across all narrations should be around 
    {narration_word_count.get(style, narration_word_count['Default'])} words (comfortable speaking pace)

    return ONLY valid JSON in this exact format:
    {{
  "title": "Engaging Video Title That Captures the Topic",
  "slides": [
    {{
      "narration_prompt": "Natural spoken text for this slide",
      "image_prompt": "Extremely detailed visual description for AI image generation including composition, lighting, mood, style, colors, and specific subjects",
      "duration": {slide_length.get(style, slide_length['Default'])}
    }},
    repeat for exactly {image_count.get(style, image_count['Default'])} slides
    ]
    }}"""

    try:
        #api call to OpenAI
        print("1. Calling OpenAI (openai api call)...")
        response = chatgpt.chat.completions.create(
            model = "gpt-4o-mini",
            messages = [
                {"role": "system", "content" : chatgpt_prompt},
                {"role": "user", "content": f"Create a {style} style video about: {prompt}"}
            ],
            temperature = 0.8,
            max_tokens = 2500
        )

        #grab and clean up the output and then it wil convert to json
        print("2. Cleaning output...")
        output_json_string = response.choices[0].message.content.strip()

        if output_json_string.startswith('```json'):
            output_json_string = output_json_string[7:]
        if output_json_string.startswith('```'):
            output_json_string = output_json_string[3:]
        if output_json_string.endswith('```'):
            output_json_string = output_json_string[:-3]

        output_json_string = output_json_string.strip()
        script_json = json.loads(output_json_string)

        #validates the json file
        print("3. Validating Json output\n")

        #length of the video 
        if len(script_json.get('slides', [])) != image_count.get(style, image_count['Default']):
            raise ValueError (f'Expected {image_count.get(style, image_count['Default'])}, got len({script_json.get('slides', [])})') 
        
        #required fields per slide
        for i, slide in enumerate(script_json['slides']):
            if not slide.get('narration_prompt'):
                raise ValueError(f"Slide {i+1} missing narration_prompt")
            if not slide.get('image_prompt'):
                raise ValueError(f"Slide {i+1} missing image_prompt")
            if not slide.get('duration'):
                raise ValueError(f"Slide {i+1} missing duration")
            
        #computes the video length
        timings = [slide['duration'] for slide in script_json['slides']]
        script_json['timings'] = timings
        total_duration = sum(timings)

        #completes it and lists the amount of slides and duration
        print("4. Script generation complete: \n")
        print(f"Script generated: {script_json['title']}")
        print(f"Total slides: {len(script_json['slides'])}")
        print(f"Total duration: {total_duration} seconds\n")

        #Style-specific duration validation
        expected_duration = video_length.get(style, video_length['Default'])
        tolerance = 10  #Allows for a 10 seconds variance

        if total_duration < (expected_duration - tolerance) or total_duration > (expected_duration + tolerance):
            print(f"WARNING: {style} video is {total_duration} seconds long, expected ~{expected_duration}s (±{tolerance}s)")

        return script_json
    
    except json.JSONDecodeError as e:
        print(f"Error parsing OpenAI resopnse as JSON: {e}")
        print(f"Response was: {output_json_string}")
        raise Exception("Failed to generated valid JSON")

    except Exception as e:
        print(f"Error generating script {e}")
        raise


def generate_visual_bible(script_data, style):
    """Generates a global visual consistency guide for image generation."""
    print("Director: generating visual bible...")

    title = script_data.get('title', '')
    prompts_summary = ' | '.join([s.get('image_prompt', '')[:80] for s in script_data.get('slides', [])])

    bible_prompt = f"""For a {style} video titled "{title}", create a concise Visual Bible to keep AI-generated images visually consistent.

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
            max_tokens=400
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


