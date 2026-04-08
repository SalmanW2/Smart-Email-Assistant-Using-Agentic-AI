from google import genai
from config_env import GEMINI_API_KEY

class AI_Engine:
    def __init__(self):
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            self.model_name = 'gemini-2.5-flash-lite'
        else:
            self.client = None

    def get_summary(self, email_body):
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = f"Provide a professional summary of this email in exactly 3 concise bullet points:\n\n{email_body}"
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception as e: 
            return f"❌ AI Error: {str(e)}"

    def generate_draft(self, instruction):
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = f"Draft a highly professional and formal business email based on this instruction: '{instruction}'. Output only the email body. Do not include subject lines or placeholders like [Your Name]."
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception as e: 
            return f"❌ AI Error: {str(e)}"

    def modify_draft(self, current_draft, user_feedback):
        if not self.client: return "⚠️ AI Error: API Key not configured."
        try:
            prompt = f"Here is the current email draft:\n{current_draft}\n\nThe user requests the following adjustments: '{user_feedback}'\n\nRewrite the draft professionally applying these changes. Output only the new email body."
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception as e: 
            return f"❌ AI Error: {str(e)}"

    def general_chat(self, text):
        if not self.client: return "I am currently offline."
        try:
            prompt = f"You are a smart, professional Email Assistant AI. The user says: '{text}'. If they are chatting casually, reply briefly in a friendly mix of Roman Urdu and English. If they are asking about emails, respond strictly in professional English and ask them to use the bot's menu."
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception: 
            return "I encountered an error processing your request. Please use the menu to navigate."

    def guest_chat(self, text):
        """Non-owners ke messages handle karne ke liye."""
        if not self.client: return "I am currently offline."
        try:
            prompt = (
                f"You are the 'Smart Email Assistant'. A guest user says: '{text}'. "
                f"Reply in a polite, friendly mix of Roman Urdu and English. "
                f"Explain that you are currently in the development phase and only providing email automation services "
                f"to your owner (Muhammad Salman). However, tell them they are welcome to chat with you generally, "
                f"and they might get full service access very soon once the development is complete."
            )
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception: 
            return "Main abhi development phase mein hu aur sirf apne owner ko serve kar raha hu. Baad mein try karein!"
