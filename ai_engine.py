import google.generativeai as genai
from config_env import GEMINI_API_KEY

class AI_Engine:
    def __init__(self):
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = self._get_working_model()
        else:
            self.model = None

    def _get_working_model(self):
        try:
            return genai.GenerativeModel('gemini-1.5-flash')
        except:
            return genai.GenerativeModel('gemini-pro')

    def detect_intent(self, user_text):
        """
        Classifies user intent into: READ, DRAFT, or CHAT.
        """
        if not self.model: return "CHAT"
        
        prompt = (
            f"User Input: '{user_text}'\n"
            "Analyze the intent strictly:\n"
            "- Return 'READ' if the user wants to check, find, or search for emails.\n"
            "- Return 'DRAFT' if the user wants to write, reply, or send an email.\n"
            "- Return 'CHAT' for greetings or unrelated queries.\n"
            "Output only the single word classification."
        )
        try:
            response = self.model.generate_content(prompt)
            intent = response.text.strip().upper()
            if "READ" in intent: return "READ"
            if "DRAFT" in intent: return "DRAFT"
            return "CHAT"
        except:
            return "CHAT"

    def get_summary(self, email_body):
        if not self.model: return "⚠️ AI Error"
        try:
            prompt = (
                f"Act as a professional executive assistant. Summarize the following email "
                f"into 3 concise bullet points. Focus on key actions and dates.\n\n"
                f"Email Body:\n{email_body}"
            )
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def generate_draft(self, original_text, user_instruction):
        if not self.model: return "⚠️ AI Error"
        try:
            prompt = (
                f"Context (Original Email): {original_text}\n"
                f"User Instruction: {user_instruction}\n\n"
                f"Draft a formal, professional email response. "
                f"Do not include placeholders like '[Your Name]'. "
                f"Keep it polite and concise."
            )
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ Error: {str(e)}"