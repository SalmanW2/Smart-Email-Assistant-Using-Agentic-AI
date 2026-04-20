import os
from google import genai
from google.genai import types
 
 
class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
 
        # Sirf Flash — free tier mein 1500 req/day, kaafi hai sab kaam ke liye
        self.model_name = 'gemini-2.0-flash'
        self.active_chats = {}
 
    # ---------------------------------------------------------------
    # Voice transcription
    # ---------------------------------------------------------------
    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    sample_file,
                    "Extract exactly what the user said in this audio. "
                    "Do not add extra words. Reply in the same language as the speaker."
                ]
            )
            return response.text
        except Exception as e:
            return f"Transcription error: {str(e)}"
 
    # ---------------------------------------------------------------
    # Email summarization (token-efficient: only called on demand)
    # ---------------------------------------------------------------
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
            return f"Summary error: {str(e)}"
 
    # ---------------------------------------------------------------
    # Agent config with Gmail tools
    # ---------------------------------------------------------------
    def _get_agent_config(self):
        tools = []
        if self.gmail:
            tools = [self.gmail.search_emails, self.gmail.send_email]
 
        system_instruction = (
            "You are a Smart Email Assistant owned by Muhammad Salman Wattoo. "
            "You help him manage his Gmail through Telegram.\n\n"
            "STRICT RULES:\n"
            "1. NO MARKDOWN. Never use asterisks (*), bold, or any formatting symbols.\n"
            "2. Be short, direct, and conversational like WhatsApp.\n"
            "3. To list or search emails, use the search_emails tool. "
            "   Example: user says 'show last 5 emails' -> call search_emails with query='label:INBOX' and max_results=5.\n"
            "4. DRAFT APPROVAL RULE: If user asks to send an email, first write the draft "
            "   and ask 'Is this okay to send? Reply yes to confirm.' "
            "   ONLY call send_email tool if the user explicitly replies yes or ok.\n"
            "5. If an attachment is mentioned, it is already cached. Just draft or send the email normally.\n"
            "6. If you do not understand, ask a simple clarifying question."
        )
 
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(enabled=True),
            temperature=0.7
        )
 
    # ---------------------------------------------------------------
    # Main agent chat (owner only)
    # ---------------------------------------------------------------
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
            # Chat session expire ho jaye to reset karke retry
            if user_id in self.active_chats:
                del self.active_chats[user_id]
            return f"Error: {str(e)}"
 
    # ---------------------------------------------------------------
    # Guest chat (anyone other than owner)
    # ---------------------------------------------------------------
    def guest_chat(self, text: str, user_id: str) -> str:
        if not self.client:
            return "Offline."
        try:
            guest_key = f"guest_{user_id}"
            if guest_key not in self.active_chats:
                system_prompt = (
                    "You are an AI assistant currently in private development. "
                    "You only serve your owner, Muhammad Salman Wattoo. "
                    "Politely decline to help other users and tell them this bot is private. "
                    "Keep replies short. No markdown."
                )
                self.active_chats[guest_key] = self.client.chats.create(
                    model=self.model_name,
                    config=types.GenerateContentConfig(system_instruction=system_prompt)
                )
            return self.active_chats[guest_key].send_message(text).text
        except Exception:
            return "Sorry, I only serve my owner Muhammad Salman Wattoo right now."
