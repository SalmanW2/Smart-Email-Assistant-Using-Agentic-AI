from google import genai
from google.genai import types
from config_env import GEMINI_API_KEY

class AI_Engine:
    def __init__(self):
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            self.model_name = 'gemini-2.5-flash-lite'
        else:
            self.client = None
        
        # Memory dictionary to remember conversations per user
        self.active_chats = {}

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

    def _get_chat_session(self, user_id, system_prompt):
        """Creates or retrieves an active memory session for the user."""
        if not self.client: return None
        
        if user_id not in self.active_chats:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7
            )
            self.active_chats[user_id] = self.client.chats.create(
                model=self.model_name,
                config=config
            )
        return self.active_chats[user_id]

    def general_chat(self, text, user_id):
        if not self.client: return "I am currently offline."
        try:
            system_prompt = (
                "You are the 'Smart Email Assistant', owned by Muhammad Salman. "
                "CRITICAL RULES: "
                "1. Keep responses VERY short, direct, and factual (1-2 sentences maximum). "
                "2. DO NOT output internal thoughts, scenarios, or formatting labels like '**Response:**'. Just output the raw conversational text. "
                "3. Speak in professional English. If the user speaks Roman Urdu, match their tone naturally, but NEVER provide translations in brackets. "
                "4. Do not act like a robot. Speak naturally."
            )
            chat = self._get_chat_session(f"owner_{user_id}", system_prompt)
            return chat.send_message(text).text
        except Exception: 
            return "I encountered an error processing your request. Please use the menu."

    def guest_chat(self, text, user_id):
        if not self.client: return "I am currently offline."
        try:
            system_prompt = (
                "You are the 'Smart Email Assistant', owned by Muhammad Salman. You are currently in the development phase. "
                "CRITICAL RULES: "
                "1. Keep responses VERY short and direct (1-2 sentences maximum). "
                "2. DO NOT output internal thoughts, scenarios, or labels. Just output the raw conversational text. "
                "3. Speak in professional English, or a friendly mix of Roman Urdu and English if the user speaks it. NEVER provide translations in brackets. "
                "4. If the user explicitly asks to read or send emails, politely explain that your email services are currently exclusive to your owner because you are in development."
            )
            chat = self._get_chat_session(f"guest_{user_id}", system_prompt)
            return chat.send_message(text).text
        except Exception: 
            return "I am currently in the development phase and only serving my owner. Please try again later."
