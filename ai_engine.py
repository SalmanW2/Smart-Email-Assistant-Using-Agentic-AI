from google import genai
from config_env import GEMINI_API_KEY

class AI_Engine:
    def __init__(self):
        if GEMINI_API_KEY:
            # Using the new SDK
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            self.model_name = 'gemini-2.5-flash' # Latest stable model
        else:
            self.client = None

    def get_summary(self, email_body):
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = f"Provide a professional summary of this email in exactly 3 concise bullet points:\n\n{email_body}"
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def generate_draft(self, instruction):
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = f"Draft a highly professional and formal business email based on this instruction: '{instruction}'. Output only the email body. Do not include subject lines or placeholders like [Your Name]."
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def modify_draft(self, current_draft, user_feedback):
        """Recreates the draft based on user feedback."""
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = (
                f"Here is the current email draft:\n{current_draft}\n\n"
                f"The user requests the following adjustments: '{user_feedback}'\n\n"
                f"Rewrite the draft professionally applying these changes. Output only the new email body."
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"❌ AI Error: {str(e)}"

    def general_chat(self, text):
        """Handles random user messages outside of the email workflows."""
        if not self.client: return "I am currently offline."
        try:
            prompt = (
                f"You are a smart, professional Email Assistant AI. The user says: '{text}'. "
                f"If they are chatting casually, reply briefly in a friendly mix of Roman Urdu and English. "
                f"If they are asking about emails, respond strictly in professional English and ask them to use the bot's menu."
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return "I encountered an error processing your request. Please use the menu to navigate."