from google import genai
from google.genai import types
from config_env import GEMINI_API_KEY

class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            self.model_name = 'gemini-2.0-flash-lite'
        else:
            self.client = None
        self.active_chats = {}

    def get_summary(self, email_body):
        if not self.client: return "AI Error: API Key missing."
        try:
            prompt = (
                "Summarize this email in 3 short points. Tone: Conversational (WhatsApp style). "
                "CRITICAL: Do NOT use Markdown formatting. No asterisks. Use standard dashes for bullets.\n\n"
                f"{email_body}"
            )
            return self.client.models.generate_content(model=self.model_name, contents=prompt).text
        except Exception as e: return f"AI Error: {str(e)}"

    def generate_draft(self, instruction):
        if not self.client: return "AI Error: API Key missing."
        prompt = f"Draft a professional email based on this: '{instruction}'. Output ONLY the email body. NO Markdown."
        return self.client.models.generate_content(model=self.model_name, contents=prompt).text

    def modify_draft(self, current_draft, user_feedback):
        prompt = f"Current draft:\n{current_draft}\nAdjustments: '{user_feedback}'\nRewrite it. Output ONLY the new email body. NO Markdown."
        return self.client.models.generate_content(model=self.model_name, contents=prompt).text

    def _get_agent_config(self):
        tools = [self.gmail.search_emails, self.gmail.send_email] if self.gmail else []
        system_instruction = (
            "You are an Agentic Email Assistant owned by Muhammad Salman. "
            "CRITICAL RULES: "
            "1. NO MARKDOWN. Never use asterisks or bold text. "
            "2. Be conversational, short, and direct (WhatsApp style). "
            "3. Search emails using 'search_emails' tool. "
            "4. DRAFT APPROVAL: If the user asks to send an email, DO NOT use 'send_email' tool immediately. First, show them the draft and ask 'Is this okay to send?'. ONLY trigger 'send_email' if the user explicitly says yes or ok. "
            "5. If they ask for changes, edit the draft and ask again."
        )
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(enabled=True),
            temperature=0.7
        )

    def agent_chat(self, text, user_id):
        if not self.client: return "System offline."
        try:
            if user_id not in self.active_chats:
                self.active_chats[user_id] = self.client.chats.create(
                    model=self.model_name, config=self._get_agent_config()
                )
            return self.active_chats[user_id].send_message(text).text
        except Exception:
            return "Error processing agent request."

    def guest_chat(self, text, user_id):
        if not self.client: return "Offline."
        try:
            prompt = "You are in development. Keep it short. Explain you only serve your owner, Muhammad Salman. NO Markdown."
            if f"guest_{user_id}" not in self.active_chats:
                self.active_chats[f"guest_{user_id}"] = self.client.chats.create(
                    model=self.model_name, 
                    config=types.GenerateContentConfig(system_instruction=prompt)
                )
            return self.active_chats[f"guest_{user_id}"].send_message(text).text
        except: return "I only serve my owner right now."
