import os
import google.generativeai as genai
from config_env import GEMINI_API_KEY

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ✅ FIX: Using STABLE model name (No '-latest')
model = genai.GenerativeModel('gemini-1.5-flash')

def summarize_email(email_body):
    try:
        prompt = f"Summarize this email in 3 short bullet points. Ignore signatures:\n\n{email_body}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"

def generate_draft_reply(original_email, instruction):
    try:
        prompt = (
            f"Original Email: {original_email}\n\n"
            f"User Intent: {instruction}\n\n"
            f"Write a professional email reply. No subject line."
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}" 