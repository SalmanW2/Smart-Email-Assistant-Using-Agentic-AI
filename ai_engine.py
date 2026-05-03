import os
from google import genai
from google.genai import types

class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.5-flash-lite"
        self.active_chats = {}
        
    def _parse_error(self, e: Exception) -> str:
        return f"Raw Error: {str(e)}"

    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[sample_file, "Translate this audio to text accurately. Do not add formatting."]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)

    # NEW: Converts user request to a pure Gmail search query
    def get_search_query(self, user_text: str) -> str:
        try:
            prompt = f"Convert this user request into a strict Gmail search query. Reply ONLY with the query string, nothing else.\nUser: {user_text}\nExamples:\nUser: search for emails from ali\nAI: from:ali\nUser: dhundo us email ko jis mein project likha ho\nAI: project"
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt]
            )
            return response.text.strip()
        except:
            return "label:INBOX"

    def get_summary(self, text: str, sender: str = "Unknown") -> str:
        try:
            prompt = f"Summarize this email concisely in 2-3 short bullet points using dashes (-). Start by explicitly stating who sent it.\nSender: {sender}\nEmail:\n{text}"
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt]
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)

    def _get_agent_config(self):
        tools = []
        if self.gmail:
            def send_new_email(to: str, subject: str, body: str) -> str:
                """Sends a new email message. Global attachments are handled automatically."""
                return self.gmail.send_email(to, subject, body, [])

            tools = [send_new_email]
            
            system_instruction = (
                "You are Muhammad Salman Wattoo's Smart Email Assistant. "
                "Speak freely and naturally in whatever language the user uses.\n\n"
                "UI/UX RULES (CRITICAL):\n"
                "1. SHORT & CLEAN: Keep responses concise. Use standard Markdown (*bold*, - bullets). NEVER use ** for bolding.\n"
                "2. DRAFTING: Present email drafts cleanly:\n"
                "   📝 *Draft Preview*\n"
                "   👤 *To:* [email]\n"
                "   🏷 *Subject:* [subject]\n"
                "   ✉️ *Message:* [body]\n"
                "   Ask for confirmation before sending. DO NOT invent attachments if the user hasn't uploaded any."
            )

        return types.GenerateContentConfig(
            tools=tools if tools else None,
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
            if user_id in self.active_chats: del self.active_chats[user_id]
            return self._parse_error(e)