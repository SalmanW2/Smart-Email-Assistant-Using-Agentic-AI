import asyncio
import json
from typing import Any
from google import genai
from google.genai import types
from config import settings
from db.memory import memory_manager
from bot.contact_manager import ContactManager
from bot.gmail_client import GmailClient

class AIEngine:
    def __init__(self) -> None:
        self.memory = memory_manager
        self.contact_manager = ContactManager()
        self.gmail_client = GmailClient()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash-lite"
        self.active_chats = {}

    def _parse_error(self, e: Exception) -> str:
        return f"System Error: {str(e)}"

    async def transcribe_audio(self, file_path: str) -> str:
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
        if self.gmail_client:
            def send_new_email(to: str, subject: str, body: str) -> str:
                """Queues a new email message for sending. Attachments previously uploaded by the user are automatically included."""
                return self.gmail_client.queue_ai_email(to, subject, body, user_id)

            def search_emails(query: str) -> str:
                """Searches the user's Gmail using a standard Gmail query (e.g., 'from:ali', 'is:unread', 'project'). Returns a list of up to 5 matching emails with their IDs, Sendernames, and Subjects."""
                service = self.gmail_client.get_service()
                if not service: return "Error: Authentication required."
                try:
                    results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
                    messages = results.get('messages', [])
                    if not messages: return "No emails found matching the query."
                    
                    output = []
                    for m in messages:
                        meta = self.gmail_client.get_email_metadata(m['id'])
                        output.append(f"Email ID: {m['id']} | From: {meta['sender']} | Subject: {meta['subject']}")
                    return "\n".join(output)
                except Exception as e:
                    return f"Search failed: {str(e)}"

            def read_email_content(msg_id: str) -> str:
                """Reads the full text content of a specific email using its ID. Use this after searching to read a specific email to the user."""
                return self.gmail_client.get_full_body(msg_id)

            def delete_email_by_id(msg_id: str) -> str:
                """Moves a specific email to the trash using its ID."""
                success = self.gmail_client.delete_email(msg_id)
                return "Email successfully moved to trash." if success else "Failed to delete email."

            tools = [send_new_email, search_emails, read_email_content, delete_email_by_id]
            
            system_instruction = (
                "You are a highly professional Smart Email Assistant powered by Google Gemini. Communicate exclusively in polite, clear, and professional English.\n\n"
                "UI/UX RULES & TOOL USAGE (CRITICAL):\n"
                "1. SHORT & CLEAN: Keep responses concise. Use standard Markdown (*bold*, - bullets).\n"
                "2. SEARCHING: Use the 'search_emails' tool when asked to find or check emails. Summarize the results nicely for the user and mention who sent them and the subjects.\n"
                "3. READING: Use the 'read_email_content' tool if the user asks to read or summarize a specific email from the search results.\n"
                "4. DELETING: Use 'delete_email_by_id' if explicitly requested to delete an email.\n"
                "5. SENDING: If the user says 'send without double checking', execute 'send_new_email' directly. Otherwise, ALWAYS present a Draft Preview for confirmation first."
            )

        return types.GenerateContentConfig(
            tools=tools if tools else None,
            system_instruction=system_instruction,
            temperature=0.2
        )

    async def agent_chat(self, text: str, user_id: str) -> str:
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

    async def process_message(self, telegram_id: int, message: str, ai_mode: bool) -> tuple[str, str | None, dict[str, Any]]:
        if not ai_mode:
            return ("AI mode is off. Please use manual email commands.", None, {"interaction_type": "system"})

        memory_prompt = await self.memory.build_memory_prompt(telegram_id)
        system_prompt = (
            "You are a professional email assistant. Use a natural, helpful tone and only make Gmail changes when the user explicitly requests it. "
            "Always keep responses concise and confirm actions before completing them."
        )

        # Use the agent_chat method for function calling
        full_prompt = system_prompt + "\n\n" + memory_prompt + "\n\n" + message
        response_text = await asyncio.to_thread(self.agent_chat, full_prompt, str(telegram_id))

        # For simplicity, assume response_text includes the result; in full implementation, parse function calls
        await self.contact_manager.extract_contacts_from_text(telegram_id, message)
        return response_text, None, {"interaction_type": "chat"}

    async def extract_and_save_contacts(self, telegram_id: int, message: str) -> None:
        await self.contact_manager.extract_contacts_from_text(telegram_id, message)

    async def process_attachment(self, telegram_id: int, file_path: str, query: str) -> str:
        prompt = f"Summarize or answer the following document request:\n{query}\n\nDocument path: {file_path}"
        
        config = types.GenerateContentConfig(
            temperature=0.2,
            system_instruction="You are a document Q&A assistant."
        )
        
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=config,
        )
        return response.text if hasattr(response, 'text') else ""

ai_engine = AIEngine()