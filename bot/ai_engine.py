import os
import json
import logging
from google import genai
from google.genai import types
from db.memory import MemoryManager
from db.contacts import ContactManager

logger = logging.getLogger(__name__)

class AI_Engine:
    def __init__(self, gmail_client):
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

    def generate_summary(self, telegram_id: int):
        """Background task to summarize chat history and save tokens."""
        recent = MemoryManager.get_recent_history(telegram_id, limit=10)
        if len(recent) < 4: return # Wait for more history
        
        history_text = "\n".join([f"User: {h['user_message']}\nBot: {h['bot_response']}" for h in reversed(recent)])
        prompt = (
            "Summarize the following conversation in 50 words or less. "
            "Extract any mentioned email addresses, names, and relationships (e.g., Boss, HR) into a JSON.\n\n"
            f"Conversation:\n{history_text}\n\n"
            "Return ONLY raw JSON: {'summary': '...', 'topic': '...', 'contacts': [{'name':'...', 'alias':'...', 'email':'...'}]}"
        )

        try:
            res = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            data = json.loads(res.text.replace("```json", "").replace("```", "").strip())
            
            # Save Memory
            MemoryManager.save_summary(telegram_id, data.get('summary', ''), {}, [], data.get('topic', 'General'))
            
            # Auto-save extracted contacts to DB mapping!
            for contact in data.get('contacts', []):
                if contact.get('email'):
                    ContactManager.upsert_contact(telegram_id, email=contact['email'], name=contact.get('name'), alias=contact.get('alias'))
        except Exception as e:
            logger.error(f"Summary Generation Error: {e}")

    def _get_agent_config(self, telegram_id: int):
        # Tools explicitly scoped to the current user via closure
        def send_new_email(to: str, subject: str, body: str) -> str:
            """Queues a new email message for sending."""
            return self.gmail.queue_ai_email(telegram_id, to, subject, body)

        def search_emails(query: str) -> str:
            """Searches the user's Gmail using a standard Gmail query."""
            service = self.gmail.get_service(telegram_id)
            if not service: return "Error: Authentication required."
            try:
                results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
                messages = results.get('messages', [])
                if not messages: return "No emails found matching the query."
                
                output = []
                for m in messages:
                    meta = self.gmail.get_email_metadata(telegram_id, m['id'])
                    output.append(f"Email ID: {m['id']} | From: {meta['sender']} | Subject: {meta['subject']}")
                return "\n".join(output)
            except Exception as e:
                return f"Search failed: {str(e)}"

        def read_email_content(msg_id: str) -> str:
            """Reads the full text content of a specific email using its ID."""
            return self.gmail.get_full_body(telegram_id, msg_id)

        def delete_email_by_id(msg_id: str) -> str:
            """Moves a specific email to the trash using its ID."""
            success = self.gmail.delete_email(telegram_id, msg_id)
            return "Email successfully moved to trash." if success else "Failed to delete email."

        tools = [send_new_email, search_emails, read_email_content, delete_email_by_id]
        
        # Inject Context & Known Contacts into the System Prompt
        recent_memory = MemoryManager.get_active_context(telegram_id)
        memory_str = "\n".join([f"- Topic: {m.get('current_topic')} | Summary: {m.get('summary_text')}" for m in recent_memory])
        
        frequent_contacts = ContactManager.get_frequent_contacts(telegram_id)
        contacts_str = "\n".join([f"- Name/Alias: {c.get('contact_alias') or c.get('contact_name')} | Email: {c.get('email_address')}" for c in frequent_contacts])

        system_instruction = (
            "You are a highly professional Smart Email Assistant powered by Agentic AI.\n"
            f"LONG-TERM MEMORY (Recent Context):\n{memory_str if memory_str else 'No recent memory.'}\n\n"
            f"KNOWN CONTACTS (Address Book):\n{contacts_str if contacts_str else 'No saved contacts.'}\n\n"
            "RULES:\n"
            "1. If the user says 'Email my boss' or mentions a name, use the KNOWN CONTACTS list to find their email address automatically.\n"
            "2. Keep responses concise. Use Markdown.\n"
            "3. If the user wants to send an email, ALWAYS present a Draft Preview first, unless they explicitly say 'send it immediately'."
        )

        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            temperature=0.2
        )

    def agent_chat(self, text: str, telegram_id: int) -> str:
        if not self.client: return "Error: AI System offline."
        try:
            if telegram_id not in self.active_chats:
                self.active_chats[telegram_id] = self.client.chats.create(
                    model=self.model_name,
                    config=self._get_agent_config(telegram_id)
                )
                
            response = self.active_chats[telegram_id].send_message(text)
            return response.text
        except Exception as e:
            if telegram_id in self.active_chats: del self.active_chats[telegram_id]
            return self._parse_error(e)