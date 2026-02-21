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
            # Updated to the latest stable endpoint to fix 404 Error
            return genai.GenerativeModel('gemini-2.0-flash')
        except:
            return genai.GenerativeModel('gemini-pro')

    def get_summary(self, email_body):
        if not self.model: return "⚠️ AI Error: Model not initialized."
        try:
            prompt = f"Provide a professional summary of this email in 3 bullet points:\n\n{email_body}"
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def generate_draft(self, instruction):
        if not self.model: return "⚠️ AI Error: Model not initialized."
        try:
            prompt = f"Draft a professional, formal email based on this intent: '{instruction}'. Do not include subject lines or placeholders like [Your Name]. Just provide the body text."
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def modify_draft(self, current_draft, user_feedback):
        """Recreates the draft based on user feedback."""
        if not self.model: return "⚠️ AI Error: Model not initialized."
        try:
            prompt = (
                f"Here is the current email draft:\n{current_draft}\n\n"
                f"The user wants the following changes: '{user_feedback}'\n\n"
                f"Rewrite the draft professionally applying these changes. Output only the new email body."
            )
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"