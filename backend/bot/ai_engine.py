import google.generativeai as genai
from config import config
from db.memory import memory_manager
from bot.contact_manager import ContactManager
from bot.gmail_client import GmailClient
import json
from typing import Tuple, Optional

genai.configure(api_key=config.GEMINI_API_KEY)

class AIEngine:
    def __init__(self):
        self.memory = memory_manager
        self.contact_manager = ContactManager()
        self.gmail_client = GmailClient()

    async def process_message(self, user_id: str, message: str, ai_mode: bool) -> Tuple[str, Optional[str]]:
        if not ai_mode:
            return "AI mode is off. Please use manual commands.", None

        # Get context
        context = await self.memory.get_conversation_context(user_id)

        # System prompt with context
        system_prompt = f"""
        You are a smart email assistant. Help users manage their emails naturally.

        Context from previous conversations:
        {context}

        Available actions:
        - Check recent emails
        - Send emails (use contact names like 'boss' or 'john@example.com')
        - Reply to emails
        - Delete emails
        - Search emails

        Respond conversationally and take actions when appropriate.
        If sending email, extract recipient from contacts or ask for clarification.
        """

        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(f"{system_prompt}\n\nUser: {message}")

        # Parse response for actions
        action = self.parse_action(response.text)

        # Extract contacts mentioned
        await self.extract_and_save_contacts(user_id, message)

        return response.text, action

    def parse_action(self, response: str) -> Optional[str]:
        # Simple parsing - in full implementation, use function calling
        if "send" in response.lower() and "email" in response.lower():
            return "send"
        elif "reply" in response.lower():
            return "reply"
        elif "delete" in response.lower():
            return "delete"
        return None

    async def extract_and_save_contacts(self, user_id: str, message: str):
        # Simple extraction - use NLP in full implementation
        words = message.split()
        for word in words:
            if "@" in word and "." in word:
                # Potential email
                name = word.split("@")[0].replace(".", " ").title()
                await self.contact_manager.save_contact(user_id, name, word)

    async def process_attachment(self, user_id: str, file_path: str, query: str) -> str:
        # Use Gemini Vision or Document AI for attachment processing
        # Simplified implementation
        model = genai.GenerativeModel('gemini-pro-vision')
        # Assume file is uploaded and accessible
        # response = model.generate_content([query, image/file])
        return "Attachment processed. Summary: [placeholder]"

    async def generate_summary(self, user_id: str, content: str) -> Tuple[str, list]:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"Summarize this conversation in 50 words and extract key facts:\n{content}"
        response = model.generate_content(prompt)
        
        # Parse summary and facts
        text = response.text
        summary = text.split("\n")[0][:50]
        facts = [line for line in text.split("\n")[1:] if line.strip()]
        
        return summary, facts

ai_engine = AIEngine()