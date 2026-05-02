import os
from google import genai
from google.genai import types
 
class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # Sab se stable aur universally free model
        self.model_name = "gemini-2.0-flash-lite"
        self.active_chats = {}
        
    def _parse_error(self, e: Exception) -> str:
        # Taki humein exact pata chale ke masla kya hai
        return f"Raw Error: {str(e)}"
 
    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[sample_file, "Translate this audio to text."]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def get_summary(self, text: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=["Summarize this email briefly:\n\n" + text]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)
 
    def _get_agent_config(self):
        tools = []
        if self.gmail:
            # Wrapper functions to fix SDK object parsing bugs
            def search_gmail_inbox(query: str, max_results: int) -> str:
                """Searches the user's Gmail inbox."""
                return self.gmail.search_emails(query, max_results)

            def send_new_email(to: str, subject: str, body: str) -> str:
                """Sends a new email message to a recipient."""
                return self.gmail.send_email(to, subject, body)

            tools = [search_gmail_inbox, send_new_email]
 
        system_instruction = (
            "You are a Smart Email Assistant. Be extremely direct. "
            "Use tools to manage Gmail. Always ask before sending."
        )
 
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            temperature=0.2
        )
 
    def agent_chat(self, text: str, user_id: str) -> str:
        if not self.client: return "Error: AI System offline."
        try:
            if user_id not in self.active_chats:
                self.active_chats[user_id] = self.client.chats.create(
                    model=self.model_name,
                    config=self._get_agent_config()
                )
            response = self.active_chats[user_id].send_message(text)
            return response.text
        except Exception as e:
            # Error hone par chat session clear karein taake loop na bane
            if user_id in self.active_chats: del self.active_chats[user_id]
            return self._parse_error(e)
 
    def guest_chat(self, text: str, user_id: str) -> str:
        return "⚠️ Unauthorized access."
