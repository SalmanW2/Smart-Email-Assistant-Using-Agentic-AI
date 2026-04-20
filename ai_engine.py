import os
from google import genai
import json

class AI_Engine:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def transcribe_audio(self, file_path):
        # Whisper jaisi capability, bina RAM crash ke
        sample_file = self.client.files.upload(file=file_path)
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[sample_file, "Extract exactly what the user said in this audio. Do not add any extra words. Reply in the same language."]
        )
        return response.text

    def get_summary(self, text):
        # Sasta Flash model tokens bachane ke liye
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=["Summarize this email strictly in 2 short lines focusing on the main point:\n" + text]
        )
        return response.text

    def analyze_intent(self, user_text):
        # Router Logic to separate Code execution from AI generation
        prompt = f"""
        Analyze the user's intent from this text: "{user_text}".
        Respond ONLY in valid JSON format with this structure:
        {{"action": "search" | "reply" | "general", "parameters": "extracted name or detail"}}
        """
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt]
        )
        try:
            # Clean possible markdown from JSON response
            cleaned = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(cleaned)
        except:
            return {"action": "general", "parameters": user_text}

    def generate_draft(self, intent_text):
        # Powerful Pro model professional emails ke liye
        response = self.client.models.generate_content(
            model='gemini-2.5-pro',
            contents=["Draft a professional, formal email based on this intent. Only output the email body:\n" + intent_text]
        )
        return response.text
        
