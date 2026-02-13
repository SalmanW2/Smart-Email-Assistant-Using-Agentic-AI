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
        Report Section 2.5.2: Intent Classification (The Router Logic).
        Decides if user wants to READ, DRAFT, or CHAT.
        """
        if not self.model: return "CHAT"
        
        prompt = (
            f"User Input: '{user_text}'\n"
            "Classify this intent into exactly one word:\n"
            "- READ (if user wants to check, read, search, or find emails)\n"
            "- DRAFT (if user wants to write, send, reply, or draft an email)\n"
            "- CHAT (if it's a general greeting or question)\n"
            "Output only the word."
        )
        try:
            response = self.model.generate_content(prompt)
            intent = response.text.strip().upper()
            # Safety cleanup
            if "READ" in intent: return "READ"
            if "DRAFT" in intent: return "DRAFT"
            return "CHAT"
        except:
            return "CHAT"

    def get_summary(self, email_body):
        if not self.model: return "⚠️ AI Error"
        try:
            prompt = f"Summarize this email in 3 short bullet points:\n\n{email_body}"
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def generate_draft(self, original_text, user_instruction):
        if not self.model: return "⚠️ AI Error"
        try:
            prompt = (
                f"Context: {original_text}\n"
                f"User Instruction: {user_instruction}\n"
                f"Write a professional email body. No Subject."
            )
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"❌ Error: {str(e)}"