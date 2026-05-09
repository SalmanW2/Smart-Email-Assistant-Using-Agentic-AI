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
        # NEW: Initialize the client using the correct modern SDK syntax
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def process_message(self, telegram_id: int, message: str, ai_mode: bool) -> tuple[str, str | None, dict[str, Any]]:
        if not ai_mode:
            return ("AI mode is off. Please use manual email commands.", None, {"interaction_type": "system"})

        memory_prompt = await self.memory.build_memory_prompt(telegram_id)
        system_prompt = (
            "You are a professional email assistant. Use a natural, helpful tone and only make Gmail changes when the user explicitly requests it. "
            "Always keep responses concise and confirm actions before completing them."
        )

        functions = self._build_functions()

        # NEW: Setup configuration and tools for the new SDK
        config = types.GenerateContentConfig(
            temperature=0.2,
            system_instruction=system_prompt + "\n\n" + memory_prompt,
            tools=[{"function_declarations": functions}]
        )

        # NEW: Calling the model using the correct method
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model="gemini-2.5-flash",
            contents=message,
            config=config,
        )

        parsed_text = self._extract_text(response)
        function_call = self._extract_function_call(response)
        
        if function_call:
            result_text, action, metadata = await self._run_function_call(telegram_id, function_call)
            await self.extract_and_save_contacts(telegram_id, message)
            return result_text, action, metadata

        await self.extract_and_save_contacts(telegram_id, message)
        return parsed_text, None, {"interaction_type": "chat"}

    def _build_functions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "send_email",
                "description": "Send a new email from the user's Gmail account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address or contact alias."},
                        "subject": {"type": "string", "description": "Email subject line."},
                        "body": {"type": "string", "description": "Email body content."},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            {
                "name": "reply_email",
                "description": "Reply to the most recent email thread.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "Gmail thread ID."},
                        "body": {"type": "string", "description": "Reply content."},
                    },
                    "required": ["thread_id", "body"],
                },
            },
            {
                "name": "delete_email",
                "description": "Delete a Gmail message by message ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_id": {"type": "string", "description": "The Gmail message ID to delete."},
                    },
                    "required": ["email_id"],
                },
            },
            {
                "name": "list_recent_emails",
                "description": "Fetch a summary of the user's most recent emails.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "description": "Number of emails to list."},
                    },
                    "required": ["count"],
                },
            },
            {
                "name": "search_emails",
                "description": "Search email subjects and senders with natural keywords.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for Gmail."},
                    },
                    "required": ["query"],
                },
            },
        ]

    def _extract_text(self, response: Any) -> str:
        if hasattr(response, 'text') and response.text:
            return response.text
        return ""

    def _extract_function_call(self, response: Any) -> dict[str, Any] | None:
        # NEW: Parsing function calls for the modern SDK
        if hasattr(response, 'function_calls') and response.function_calls:
            fc = response.function_calls[0]
            return {
                "name": fc.name,
                "arguments": fc.args
            }
        return None

    async def _run_function_call(self, telegram_id: int, function_call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        name = function_call.get("name")
        arguments = function_call.get("arguments", {})
        
        # Safely handle arguments whether they are dict or string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}

        if name == "send_email":
            recipient = await self.contact_manager.resolve_contact(telegram_id, arguments.get("to", ""))
            success = await self.gmail_client.send_email(telegram_id, recipient, arguments.get("subject", ""), arguments.get("body", ""))
            return (
                "Email sent successfully." if success else "Unable to send the email. Please check your account connection.",
                "send",
                {"interaction_type": "send_email", "details": arguments},
            )

        if name == "reply_email":
            success = await self.gmail_client.reply_email(telegram_id, arguments.get("thread_id", ""), arguments.get("body", ""))
            return (
                "Reply sent successfully." if success else "Unable to reply to the email.",
                "reply",
                {"interaction_type": "reply_email", "details": arguments},
            )

        if name == "delete_email":
            success = await self.gmail_client.delete_email(telegram_id, arguments.get("email_id", ""))
            return (
                "Email deleted successfully." if success else "Unable to delete that email.",
                "delete",
                {"interaction_type": "delete_email", "details": arguments},
            )

        if name == "list_recent_emails":
            emails = await self.gmail_client.get_recent_emails(telegram_id, count=arguments.get("count", 5))
            summary = "\n".join([f"- {email['subject']} from {email['sender']}" for email in emails[:5]])
            return (f"Here are your recent emails:\n{summary}", None, {"interaction_type": "list_recent_emails"})

        if name == "search_emails":
            results = await self.gmail_client.search_emails(telegram_id, arguments.get("query", ""))
            formatted = "\n".join([f"- {item['subject']} from {item['sender']}" for item in results[:5]])
            return (f"Search results:\n{formatted}", None, {"interaction_type": "search_emails"})

        return ("I processed your request, but no direct Gmail action was required.", None, {"interaction_type": "chat"})

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
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return self._extract_text(response)

ai_engine = AIEngine()