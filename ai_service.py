import os
import google.generativeai as genai
from config_env import GEMINI_API_KEY

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("❌ Error: GEMINI_API_KEY not found in .env")

# ✅ FIX: Removed '-latest' to solve 404 Error
model = genai.GenerativeModel('gemini-1.5-flash')

def summarize_email(email_body):
    """Summarizes email into 3 bullet points."""
    try:
        prompt = f"Summarize this email in 3 short bullet points. Ignore signatures:\n\n{email_body}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"

def generate_draft_reply(original_email, instruction):
    """Generates a professional reply based on instruction."""
    try:
        prompt = (
            f"Original Email: {original_email}\n\n"
            f"User Intent: {instruction}\n\n"
            f"Write a professional email reply. No subject line, just body text."
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"