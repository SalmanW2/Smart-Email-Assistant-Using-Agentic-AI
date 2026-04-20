import os
from google import genai
from google.genai import types

class AI_Engine:
    def __init__(self, gmail_client=None):
        self.gmail = gmail_client
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # Sasta aur fast model summaries/guest ke liye
        self.model_name = 'gemini-2.5-flash' 
        # Heavy model complex reasoning aur function calling ke liye
        self.pro_model = 'gemini-2.5-pro'   
        self.active_chats = {}

    def transcribe_audio(self, file_path):
        sample_file = self.client.files.upload(file=file_path)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[sample_file, "Extract exactly what the user said in this audio. Do not add extra words. Reply in the same language."]
        )
        return response.text

    def get_summary(self, text):
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=["Summarize this email strictly in 2 short lines focusing on the main point:\n" + text]
        )
        return response.text

    def _get_agent_config(self):
        tools = [self.gmail.search_emails, self.gmail.send_email] if self.gmail else []
        system_instruction = (
            "You are an Agentic Email Assistant owned by Muhammad Salman Wattoo. "
            "CRITICAL RULES: "
            "1. NO MARKDOWN. Never use asterisks or bold text. "
            "2. Be conversational, short, and direct (WhatsApp style). "
            "3. If the user asks for 'last 5 emails' or 'latest emails', use 'search_emails' tool with query='label:INBOX' and max_results to the requested number. "
            "4. DRAFT APPROVAL: If the user asks to send an email, DO NOT use 'send_email' tool immediately. First, show them the draft and ask 'Is this okay to send?'. ONLY trigger 'send_email' if the user explicitly says yes or ok. "
            "5. If an attachment is uploaded, the system will cache it. Just proceed with drafting or sending the email normally."
        )
        return types.GenerateContentConfig(
            tools=tools,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(enabled=True),
            temperature=0.7
        )

    def agent_chat(self, text, user_id):
        if not self.client: return "System offline."
        try:
            if user_id not in self.active_chats:
                self.active_chats[user_id] = self.client.chats.create(
                    model=self.pro_model, 
                    config=self._get_agent_config()
                )
            return self.active_chats[user_id].send_message(text).text
        except Exception as e:
            return f"Error processing agent request: {str(e)}"

    def guest_chat(self, text, user_id):
        if not self.client: return "Offline."
        try:
            prompt = "You are an AI assistant in development. Keep it short. Explicitly explain you only serve your owner, Muhammad Salman Wattoo. NO Markdown."
            if f"guest_{user_id}" not in self.active_chats:
                self.active_chats[f"guest_{user_id}"] = self.client.chats.create(
                    model=self.model_name, 
                    config=types.GenerateContentConfig(system_instruction=prompt)
                )
            return self.active_chats[f"guest_{user_id}"].send_message(text).text
        except: 
            return "I only serve my owner, Muhammad Salman Wattoo, right now."
