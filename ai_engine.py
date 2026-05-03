import os
from google import genai
from google.genai import types
 
class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # FIXED: Updated to the new working model
        self.model_name = "gemini-2.5-flash"
        self.active_chats = {}
        self.last_auth_state = False
        
    def _parse_error(self, e: Exception) -> str:
        return f"Raw Error: {str(e)}"
 
    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[sample_file, "Translate this audio to text accurately."]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def get_summary(self, text: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=["Summarize this email in 2 short lines:\n\n" + text]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def _get_agent_config(self, is_logged_in):
        tools = []
        if is_logged_in and self.gmail:
            def search_gmail_inbox(query: str, max_results: int) -> str:
                """Searches the user's Gmail inbox."""
                return self.gmail.search_emails(query, max_results)

            def send_new_email(to: str, subject: str, body: str) -> str:
                """Sends a new email message."""
                return self.gmail.send_email(to, subject, body)

            tools = [search_gmail_inbox, send_new_email]
            
            system_instruction = (
                "You are Muhammad Salman Wattoo's Smart Email Assistant. "
                "You are connected to his Gmail. Use tools to read or send emails. "
                "Always ask for approval before sending an email. Keep it short and direct."
            )
        else:
            # AI ko pata hoga ke user login nahi hai
            system_instruction = (
                "You are a Smart Email Assistant. The user is currently NOT logged into Google. "
                "You CANNOT read or send emails right now. If the user asks for anything related to emails, "
                "politely tell them: '⚠️ Please send /start to connect your Google Account first.' "
                "You can answer general questions normally."
            )
 
        return types.GenerateContentConfig(
            tools=tools if tools else None,
            system_instruction=system_instruction,
            temperature=0.2
        )
 
    def agent_chat(self, text: str, user_id: str) -> str:
        if not self.client: return "Error: AI System offline."
        try:
            # Check current auth state
            current_auth_state = bool(self.gmail.get_service() if self.gmail else False)
            
            # Agar user ne abhi abhi login kiya hai, toh chat session refresh karo taake tools mil jayein
            if self.last_auth_state != current_auth_state:
                if user_id in self.active_chats:
                    del self.active_chats[user_id]
                self.last_auth_state = current_auth_state

            if user_id not in self.active_chats:
                self.active_chats[user_id] = self.client.chats.create(
                    model=self.model_name,
                    config=self._get_agent_config(current_auth_state)
                )
                
            response = self.active_chats[user_id].send_message(text)
            return response.text
        except Exception as e:
            if user_id in self.active_chats: del self.active_chats[user_id]
            return self._parse_error(e)
 
    def guest_chat(self, text: str, user_id: str) -> str:
        return "⚠️ Unauthorized access. This is a private assistant."
