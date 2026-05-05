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
        return f"System Error: {str(e)}"

    def transcribe_audio(self, file_path: str) -> str:
        try:
            sample_file = self.client.files.upload(file=file_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[sample_file, "Transcribe this audio accurately. Do not invent words if it is noisy. If the audio is completely unintelligible, just output: '[Audio Unclear]'."]
            )
            return response.text.strip()
        except Exception as e:
            return self._parse_error(e)

    def get_search_query(self, user_text: str) -> str:
        try:
            prompt = f"Convert this user request into a strict Gmail search query. Reply ONLY with the query string, nothing else.\nUser: {user_text}\nExamples:\nUser: search for emails from ali\nAI: from:ali\nUser: find project emails\nAI: project"
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

    def _get_agent_config(self, user_id: str):
        tools = []
        if self.gmail:
            def send_new_email(to: str, subject: str, body: str) -> str:
                """Queues a new email message for sending. Attachments previously uploaded by the user are automatically included."""
                return self.gmail.queue_ai_email(to, subject, body, user_id)

            tools = [send_new_email]
            
            system_instruction = (
                "You are a highly professional Smart Email Assistant. Communicate exclusively in polite, clear, and professional English.\n\n"
                "UI/UX RULES (CRITICAL):\n"
                "1. SHORT & CLEAN: Keep responses concise. Use standard Markdown (*bold*, - bullets).\n"
                "2. ERROR HANDLING: If a system tool returns an error, explain the issue gracefully.\n"
                "3. DRAFTING & SENDING CONFIRMATION:\n"
                "   - IMMEDIATE SEND: If the user explicitly says 'send without double checking' or 'direct send', execute the 'send_new_email' tool. Inform the user that the email is queued and they have a few seconds to undo it via the button.\n"
                "   - DOUBLE CHECK (DRAFT PREVIEW): If they ask to double check, or if the content is highly sensitive/formal, present a draft preview first.\n"
                "     📝 *Draft Preview*\n"
                "     👤 *To:* [email]\n"
                "     🏷 *Subject:* [subject]\n"
                "     ✉️ *Message:* [body]\n"
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
                    config=self._get_agent_config(user_id)
                )
                
            response = self.active_chats[user_id].send_message(text)
            return response.text
        except Exception as e:
            if user_id in self.active_chats: del self.active_chats[user_id]
            return self._parse_error(e)