import os
from google import genai
from google.genai import types

class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.5-flash-lite"
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
                "Speak freely and naturally in whatever language the user uses.\n\n"
                "UI/UX & SEARCH RULES (CRITICAL):\n"
                "1. SHORT & CLEAN: Keep responses concise. Use standard Markdown (*bold*, - bullets). NEVER use ** for bolding.\n"
                "2. SMART SEARCHING: When asked to search for a person, DO NOT use strict 'from:' operators immediately. Use broad keyword searches (e.g., just the person's name) to catch variations.\n"
                "3. SMART MATCHING ANALYSIS: After searching, analyze the senders of the emails found. If the sender's name is NOT a 100% exact match to what the user asked for (e.g., user asked for 'Affan Alim' but you found 'Muhammad Affan'), politely and professionally inform the user. Say something like: 'I couldn't find an exact match for X, but I found similar results from Y' or 'I found emails mentioning X'.\n"
                "4. DRAFTING: Present email drafts cleanly:\n"
                "   📝 *Draft Preview*\n"
                "   👤 *To:* [email]\n"
                "   🏷 *Subject:* [subject]\n"
                "   ✉️ *Message:* [body]\n"
                "   Ask for confirmation before sending."
            )
        else:
            system_instruction = (
                "You are a Smart Email Assistant. The user is currently NOT logged into Google. "
                "Tell them: '⚠️ Please send /start to connect your Google Account first.'"
            )

        return types.GenerateContentConfig(
            tools=tools if tools else None,
            system_instruction=system_instruction,
            temperature=0.2
        )

    def agent_chat(self, text: str, user_id: str) -> str:
        if not self.client: return "Error: AI System offline."
        try:
            current_auth_state = bool(self.gmail.get_service() if self.gmail else False)
            
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
