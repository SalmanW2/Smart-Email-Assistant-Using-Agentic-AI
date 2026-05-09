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
        # Kept for manual UI search button compatibility
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

            def search_emails(query: str) -> str:
                """Searches the user's Gmail using a standard Gmail query (e.g., 'from:ali', 'is:unread', 'project'). Returns a list of up to 5 matching emails with their IDs, Sendernames, and Subjects."""
                service = self.gmail.get_service()
                if not service: return "Error: Authentication required."
                try:
                    results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
                    messages = results.get('messages', [])
                    if not messages: return "No emails found matching the query."
                    
                    output = []
                    for m in messages:
                        meta = self.gmail.get_email_metadata(m['id'])
                        output.append(f"Email ID: {m['id']} | From: {meta['sender']} | Subject: {meta['subject']}")
                    return "\n".join(output)
                except Exception as e:
                    return f"Search failed: {str(e)}"

            def read_email_content(msg_id: str) -> str:
                """Reads the full text content of a specific email using its ID. Use this after searching to read a specific email to the user."""
                return self.gmail.get_full_body(msg_id)

            def delete_email_by_id(msg_id: str) -> str:
                """Moves a specific email to the trash using its ID."""
                success = self.gmail.delete_email(msg_id)
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