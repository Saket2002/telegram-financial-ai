import os
import uvicorn
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

# In-memory session store (Replace with PostgreSQL query in production)
user_states = {}

SYSTEM_PROMPT = """
You are an executive AI Financial Analyst inside Telegram.
Your primary objective is saving the user time by surfacing actionable financial intelligence.

Rules:
1. Speak concisely like a senior equity research analyst or VP of Finance.
2. Focus on WHY metrics move and WHAT matters for decisions.
3. Format output cleanly using Telegram Markdown (bolding key figures, clear bullet points).
4. Do NOT mention slash commands, menus, or buttons. Keep everything conversational.
"""

async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as http_client:
        await http_client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
        )

async def handle_conversational_onboarding(chat_id: int, user_text: str):
    state = user_states.get(chat_id, {"step": 0, "role": None, "watchlist": []})
    
    if state["step"] == 0:
        welcome_text = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor my research and market briefings to your daily workflow, "
            "**what best describes your role?** (e.g., Investor, Analyst, Founder, Finance Student, or Corporate Finance)"
        )
        user_states[chat_id] = {"step": 1, "role": None, "watchlist": []}
        await send_message(chat_id, welcome_text)
        return True

    elif state["step"] == 1:
        state["role"] = user_text
        state["step"] = 2
        user_states[chat_id] = state
        
        reply = (
            f"Got it—customizing insights for a **{user_text}**.\n\n"
            "Which key companies, tickers, or sectors do you follow most closely? "
            "(e.g., *Nvidia, Apple, Indian Banking Sector, Semiconductor industry*)"
        )
        await send_message(chat_id, reply)
        return True

    elif state["step"] == 2:
        state["watchlist"] = [item.strip() for item in user_text.split(",")]
        state["step"] = 3 # Onboarding finished
        user_states[chat_id] = state
        
        confirmation = (
            f"Perfect. I've locked in your focus areas: **{', '.join(state['watchlist'])}**.\n\n"
            "I will tailor all financial research, metric comparisons, and briefings to these priorities. "
            "How can I assist your workflow right now?"
        )
        await send_message(chat_id, confirmation)
        return True

    return False # Onboarding complete, proceed to normal AI workflow

async def process_and_reply(chat_id: int, user_text: str):
    # Check if user needs or is currently in onboarding
    if chat_id not in user_states or user_states[chat_id]["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "/start", "start"]:
            user_states[chat_id] = {"step": 0, "role": None, "watchlist": []}
        is_onboarding = await handle_conversational_onboarding(chat_id, user_text)
        if is_onboarding:
            return

    # Normal Conversational AI Workflow with Memory Context
    user_profile = user_states.get(chat_id, {})
    role_context = f"User Role: {user_profile.get('role', 'Finance Professional')}\nWatchlist: {', '.join(user_profile.get('watchlist', []))}"
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{role_context}"},
                {"role": "user", "content": user_text}
            ],
            temperature=0.2
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Analysis Error: {str(e)}"

    await send_message(chat_id, reply)

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text")

    if chat_id and user_text:
        background_tasks.add_task(
            process_and_reply, 
            chat_id=chat_id, 
            user_text=user_text
        )

    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
