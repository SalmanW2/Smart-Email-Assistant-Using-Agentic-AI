import os
import sys
import asyncio

# The user will provide the .env file containing the real API keys.
from dotenv import load_dotenv
load_dotenv() # Load the .env file explicitly before importing config

# Append backend to path so imports work natively
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.ai_engine import ai_engine

test_cases = [
    "Abdullah ko email bhejo k Friday ki party on hai ya nahi.",
    "yr kal walay abdullah ko nai, danish ko mail draft karo k viva kab hai?",
    "Bhai jaan ek email likh do sir naveed ko FYP report k baray mein aur attach bhi karni hai file.",
    "Hello, mera inbox kaisa chal raha hai aaj?",
    "kia tum sach ma smart ho ya just script ho?",
    "exam schedule aa gya final ka?",
    "Meri last 7 emails do jo mene receive ki hain.",
    "5 ghanta pehle ki received emails mein dekho meri FYP report approve ho gai kya?",
    "zaphyre ki taraf se koi recruitment ki email aayi hai iqra university wale account par?",
    "UNV platform ki registration wali email dhoond kar batao usme link kya tha.",
    "check karo mene danish ko last week kya bheja tha.",
    "is pdf file ko parho aur batao isme similarity report kitni hai.",
    "jo file mene abhi attach ki hai, usko summarize karke email banao.",
    "mail kro... nai ruk jao, pehle inbox check karo koi nayi mail to nai aayi.",
    "muhammad salman wattoo ko forward kar do meri last aayi hui email.",
    "draft an email for the junior developer position and also show me 18% profit rates email.",
    "Hye",
    "last 5.",
    "is file ko read kr k batao k bachelors ka last semester kab khatam hoga.",
    "send a mail to hr@company.com saying I upgraded my Upaisa wallet."
]

async def run_simulation():
    # Use a dummy telegram_id for simulation
    telegram_id = 999999
    
    print("      --- STARTING ORCHESTRATOR-WORKER SIMULATION ---")
    
    for i, user_query in enumerate(test_cases, 1):
        print(f"[{i}/20] USER: {user_query}")
        
        try:
            # 1. Test Groq Intent Routing specifically
            route = await ai_engine._groq_intent_router(user_query, telegram_id)
            intent = route.get("intent", "UNKNOWN")
            print(f"       -> GROQ INTENT: {intent}")
            print(f"       -> GROQ RAW JSON: {route}")
            
            # 2. Test Full Pipeline (agent_chat)
            final_response = await ai_engine.agent_chat(user_query, telegram_id)
            
            # Formatting the output to make it readable in the terminal
            safe_resp = final_response.replace('\n', ' ')
            if len(safe_resp) > 150:
                safe_resp = safe_resp[:150] + "..."
            
            print(f"       -> FINAL ROUTING/RESPONSE: {safe_resp}")
        except Exception as e:
            print(f"       -> ERROR: {e}")
        
        print("-" * 60)
        
        # Adding a small delay to avoid rapid rate-limits during simulation
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run_simulation())
