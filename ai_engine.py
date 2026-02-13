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
        """Prevents 404 Error by finding the correct model name."""
        try:
            # First try the standard stable version
            model = genai.GenerativeModel('gemini-1.5-flash')
            return model
        except:
            # Fallback
            return genai.GenerativeModel('gemini-pro')

    def get_summary(self, email_body):
        """Summarizes email as per Use Case UC-02."""
        if not self.model: return "⚠️ AI Error: API Key Missing"
        try:
            prompt = f"Summarize this email in 3 short bullet points. Ignore signatures:\n\n{email_body}"
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def generate_draft(self, original_text, user_instruction):
        """Drafts reply as per Use Case UC-03."""
        if not self.model: return "⚠️ AI Error: API Key Missing"
        try:
            prompt = (
                f"Original Email: {original_text}\n\n"
                f"User Intent: {user_instruction}\n\n"
                f"Write a professional email reply. No subject line."
            )
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"