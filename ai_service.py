import google.generativeai as genai
from config_env import GEMINI_API_KEY

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ✅ FIX: Stable model name (No '-latest') to prevent 404 errors
model = genai.GenerativeModel('gemini-1.5-flash')

def summarize_email(email_body):
    """Generates a formal summary."""
    try:
        prompt = (
            f"Analyze the following email and provide a professional summary "
            f"in 3 concise bullet points. Exclude signatures and disclaimers:\n\n{email_body}"
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"

def generate_draft_reply(original_email, instruction, current_draft=None):
    """Generates or refines a professional email draft."""
    try:
        if current_draft:
            # Edit Mode
            prompt = (
                f"Current Draft:\n{current_draft}\n\n"
                f"User Feedback/Correction: {instruction}\n\n"
                f"Refine the draft based on the feedback. Maintain a professional tone. "
                f"Do not include placeholders like '[Your Name]'."
            )
        else:
            # New Draft Mode
            prompt = (
                f"Original Email:\n{original_email}\n\n"
                f"User Instruction: {instruction}\n\n"
                f"Draft a formal and professional reply. Do not include a subject line. "
                f"Ensure the tone is polite and business-appropriate."
            )
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"