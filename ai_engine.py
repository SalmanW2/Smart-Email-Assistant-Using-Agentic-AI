import os
from google import genai
from google.genai import types
 
class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.5-flash-lite"
        self.active_chats = {}
        
    # FIXED: Clean, user-friendly error messages (No raw tracebacks)
    def _parse_error(self, e: Exception) -> str:
        error_str = str(e).lower()
        if "quota" in error_str or "429" in error_str:
            return "QUOTA_ERROR: AI limits reached."
        elif "api key" in error_str or "401" in error_str:
            return "Error: Gemini Authentication missing."
        else:
            return "Error: AI System temporarily unavailable."
 
    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    sample_file,
                    "Extract exactly what the user said in this audio. "
                    "Do not add extra words. Reply in the exact same language (e.g. Urdu/English) as the speaker."
                ]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def get_summary(self, text: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    "Summarize this email in exactly 2 short lines. "
                    "Focus only on the main point and what action is needed. "
                    "No markdown, no asterisks:\n\n" + text
                ]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def _get_agent_config(self):
        tools = []
        if self.gmail:
            tools = [self.gmail.search_emails, self.gmail.send_email]
 
        system_instruction = (
            "You are a Smart Email Assistant owned by Muhammad Salman Wattoo. "
            "You help him manage his Gmail through Telegram.\n\n"
            "STRICT RULES TO SAVE API QUOTA:\n"
            "1. NO MARKDOWN. Never use asterisks (*), bold, or any formatting symbols.\n"
            "2. Be extremely short and direct.\n"
            "3. DO NOT search or fetch past emails unless the user explicitly asks for them.\n"
            "4. To list emails, use the search_emails tool. "
            "   Example: user says 'show last 5 emails' -> call search_emails with query='label:INBOX' and max_results=5.\n"
            "5. DRAFT APPROVAL RULE: If user asks to send an email, first write the draft "
            "   and ask 'Is this okay to send? Reply yes to confirm.' "
            "   ONLY call send_email tool if the user explicitly replies yes or ok.\n"
            "6. If an attachment is mentioned, it is already cached. Just draft or send the email normally.\n"
            "7. If you do not understand, ask a simple clarifying question."
        )
 
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(enabled=True),
            temperature=0.3 
        )
 
    def agent_chat(self, text: str, user_id: str) -> str:
        if not self.client:
            return "System offline."
        try:
            if user_id not in self.active_chats:
                self.active_chats[user_id] = self.client.chats.create(
                    model=self.model_name,
                    config=self._get_agent_config()
                )
            response = self.active_chats[user_id].send_message(text)
            return response.text
        except Exception as e:
            if user_id in self.active_chats:
                del self.active_chats[user_id]
            return self._parse_error(e)
 
    def guest_chat(self, text: str, user_id: str) -> str:
        return "⚠️ This is a private assistant owned by Muhammad Salman Wattoo. Unauthorized access."