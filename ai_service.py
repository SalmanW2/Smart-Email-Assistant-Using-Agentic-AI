import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

# --- CONFIGURATION ---
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("❌ Error: GEMINI_API_KEY not found in .env")

# Model Setup (Flash is fast & free)
model = genai.GenerativeModel('gemini-1.5-flash')

def summarize_email(email_body):
    """
    Summarizes long emails into 3 bullet points.
    """
    if not API_KEY: return "⚠️ AI Error: API Key Missing."
    
    try:
        prompt = (
            f"Summarize this email in 3 short, punchy bullet points. "
            f"Ignore signatures and legal disclaimers:\n\n{email_body}"
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"

def generate_draft_reply(original_email_body, user_instruction):
    """
    Generates a reply based on user's short instruction.
    """
    if not API_KEY: return "⚠️ AI Error: API Key Missing."

    try:
        prompt = (
            f"You are a professional email assistant. "
            f"The user received this email:\n'{original_email_body}'\n\n"
            f"The user wants to reply with this intent:\n'{user_instruction}'\n\n"
            f"Write a professional, polite, and clear email reply. "
            f"Do NOT include a subject line. Write ONLY the body text."
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"