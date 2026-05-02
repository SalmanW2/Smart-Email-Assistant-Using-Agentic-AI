import os
from google import genai
from google.genai import types
 
class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-1.5-flash"
        self.active_chats = {}
        
    def _parse_error(self, e: Exception) -> str:
        """
        Parses raw API exceptions and returns professional, human-readable error messages.
        """
        error_str = str(e).lower()
        if "quota" in error_str or "429" in error_str:
            return "Error: AI quota has been exhausted. Please change the model or try again tomorrow."
        elif "api key" in error_str or "401" in error_str or "unauthorized" in error_str:
            return "Error: Invalid or missing API Key. Please verify your credentials."
        elif "timeout" in error_str or "network" in error_str or "connection" in error_str:
            return "Error: Network connection to the AI server was lost. Please try again."
        elif "model" in error_str or "not found" in error_str or "404" in error_str:
            return "Error: The specified AI model was not found. Please verify the model configuration."
        else:
            return f"Error: {str(e)}"
 
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
            # FIXED: Wrapping class methods in standard functions avoids the "Error: OBJECT" SDK bug completely.
            def search_gmail_inbox(query: str, max_results: int = 5) -> str:
                """Searches the user's Gmail inbox using standard search queries like 'is:unread'."""
                return self.gmail.search_emails(query, max_results)

            def send_new_email(to: str, subject: str, body: str) -> str:
                """Drafts and sends a new email message to the specified recipient."""
                return self.gmail.send_email(to, subject, body)

            tools = [search_gmail_inbox, send_new_email]
 
        system_instruction = (
            "You are a Smart Email Assistant owned by Muhammad Salman Wattoo. "
            "You help him manage his Gmail through Telegram.\n\n"
            "STRICT RULES TO SAVE API QUOTA:\n"
            "1. NO MARKDOWN. Never use asterisks (*), bold, or any formatting symbols.\n"
            "2. Be extremely short and direct.\n"
            "3. DO NOT search or fetch past emails unless the user explicitly asks for them.\n"
            "4. To list emails, use the search_gmail_inbox tool. "
            "   Example: user says 'show last 5 emails' -> call search_gmail_inbox with query='label:INBOX' and max_results=5.\n"
            "5. DRAFT APPROVAL RULE: If user asks to send an email, first write the draft "
            "   and ask 'Is this okay to send? Reply yes to confirm.' "
            "   ONLY call send_new_email tool if the user explicitly replies yes or ok.\n"
            "6. If an attachment is mentioned, it is already cached. Just draft or send the email normally.\n"
            "7. If you do not understand, ask a simple clarifying question."
        )
 
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            temperature=0.3 
        )
 
    def agent_chat(self, text: str, user_id: str) -> str:
        if not self.client:
            return "Error: AI System offline."
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
        return "⚠️ This is a private assistant owned by Muhammad Salman Wattoo. Unauthorized access is prohibited."