import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

class AIEngine:
    """
    Wraps Google Gemini API for NLU and Generation.
    Ref: Section 5.4 of Project Report.
    """
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        self._configure()

    def _configure(self):
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Using Flash model as per report
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            print("❌ Error: GEMINI_API_KEY not found in .env")

    def summarize_email(self, email_body):
        """Summarizes long emails into 3 bullet points."""
        if not self.model: return "⚠️ AI Error: API Key Missing."
        
        try:
            prompt = (
                f"Summarize this email in 3 short, punchy bullet points. "
                f"Ignore signatures and legal disclaimers:\n\n{email_body}"
            )
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def generate_draft_reply(self, original_email_body, user_instruction):
        """Generates a reply based on user's instruction."""
        if not self.model: return "⚠️ AI Error: API Key Missing."

        try:
            prompt = (
                f"You are a professional email assistant. "
                f"The user received this email:\n'{original_email_body}'\n\n"
                f"The user wants to reply with this intent:\n'{user_instruction}'\n\n"
                f"Write a professional, polite, and clear email reply. "
                f"Do NOT include a subject line. Write ONLY the body text."
            )
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"