import os
import re
import uvicorn
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI
from groq import Groq

app = FastAPI()

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Initialize Clients
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

openai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

# In-Memory User Profiles Store
user_profiles = {}

SYSTEM_PROMPT = """
You are an executive AI Financial Analyst inside Telegram.
Your primary job is delivering live, actionable financial intelligence concisely to save users time.

CRITICAL INSTRUCTIONS:
1. Always prioritize the provided 'Live Market Context' for current stock prices and valuation metrics.
2. NEVER mention knowledge cutoffs, training dates, or tell the user to check external websites.
3. Use clean Telegram Markdown formatting (bold key figures, clear bullet points).
4. Keep all interactions conversational and executive—avoid slash commands or menu language.
"""

# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def send_message(chat_id: int, text: str):
    """Sends Markdown formatted message back to Telegram user"""
    async with httpx.AsyncClient() as http_client:
        await http_client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
        )

async def fetch_finnhub_quote(symbol: str) -> str:
    """Fetches live stock quotes directly from Finnhub API"""
    if not FINNHUB_API_KEY:
        return ""
    
    symbol = symbol.strip().upper()
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"

    try:
        async with httpx.AsyncClient() as client_http:
            res = await client_http.get(url, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                current_price = data.get("c")
                prev_close = data.get("pc")
                
                if current_price and current_price > 0:
                    change_pct = round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close else 0
                    return (
                        f"REAL-TIME MARKET DATA FOR {symbol}:\n"
                        f"- Current Price: ${current_price:.2f} USD\n"
                        f"- Today's Change: {change_pct}%\n"
                        f"- Previous Close: ${prev_close:.2f} USD"
                    )
    except Exception as e:
        print(f"Finnhub fetch error for {symbol}: {e}")

    return ""

async def transcribe_telegram_voice(file_id: str) -> str:
    """Fetches Telegram voice note .ogg file and transcribes via Groq Whisper"""
    if not groq_client:
        return ""

    async with httpx.AsyncClient() as http_client:
        file_info_res = await http_client.get(
            f"{TELEGRAM_API_URL}/getFile",
            params={"file_id": file_id}
        )
        if file_info_res.status_code != 200:
            return ""

        file_path = file_info_res.json()["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

        audio_res = await http_client.get(download_url)
        if audio_res.status_code != 200:
            return ""

        audio_bytes = audio_res.content

    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice_note.ogg", audio_bytes),
            model="whisper-large-v3-turbo",
            response_format="text"
        )
        return transcription
    except Exception as e:
        print(f"Whisper Transcription Error: {e}")
        return ""

# ==========================================
# ONBOARDING FLOW
# ==========================================

async def handle_onboarding(chat_id: int, user_text: str) -> bool:
    """Conversational onboarding sequence asking for role and watchlist"""
    profile = user_profiles.get(chat_id, {"step": 0, "role": None, "watchlist": []})
    
    if profile["step"] == 0:
        greeting = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor research and briefings to your workflow, "
            "**what best describes your role?** (e.g., *Investor, Equity Analyst, Founder, VP of Finance*)"
        )
        user_profiles[chat_id] = {"step": 1, "role": None, "watchlist": []}
        await send_message(chat_id, greeting)
        return True

    elif profile["step"] == 1:
        profile["role"] = user_text
        profile["step"] = 2
        user_profiles[chat_id] = profile
        
        reply = (
            f"Got it—customizing intelligence for a **{user_text}**.\n\n"
            "Which key companies, tickers, or sectors do you follow most closely? "
            "(e.g., *Nvidia, Apple, TSLA, Semiconductor industry*)"
        )
        await send_message(chat_id, reply)
        return True

    elif profile["step"] == 2:
        watchlist_items = [item.strip().upper() for item in user_text.split(",")]
        profile["watchlist"] = watchlist_items
        profile["step"] = 3  # Onboarding complete
        user_profiles[chat_id] = profile
        
        confirmation = (
            f"Perfect. I've configured your focus areas: **{', '.join(watchlist_items)}**.\n\n"
            "I will tailor all financial research, metric comparisons, and briefings to these priorities. "
            "How can I assist your workflow right now?"
        )
        await send_message(chat_id, confirmation)
        return True

    return False

# ==========================================
# MAIN PROCESSING ENGINE
# ==========================================

async def process_and_reply(chat_id: int, user_text: str = None, voice_file_id: str = None):
    # Handle voice note transcription if present
    if voice_file_id and not user_text:
        await send_message(chat_id, "🎙️ *Transcribing voice message...*")
        user_text = await transcribe_telegram_voice(voice_file_id)

        if not user_text or not user_text.strip():
            await send_message(chat_id, "Sorry, I couldn't transcribe that voice message. Please try speaking clearly or send text.")
            return

        await send_message(chat_id, f"📝 *Transcribed:* \"_{user_text}_\"")

    if not user_text:
        return

    # Trigger conversational onboarding for new users or restart keywords
    if chat_id not in user_profiles or user_profiles[chat_id]["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "start", "/start"]:
            user_profiles[chat_id] = {"step": 0, "role": None, "watchlist": []}
        if await handle_onboarding(chat_id, user_text):
            return

    # Extract ticker / company name from query
    name_map = {
        "NVIDIA": "NVDA", "APPLE": "AAPL", "MICROSOFT": "MSFT", 
        "GOOGLE": "GOOGL", "AMAZON": "AMZN", "TESLA": "TSLA", "META": "META"
    }
    
    target_ticker = None
    for word in user_text.upper().split():
        clean_word = re.sub(r'[^A-Z]', '', word)
        if clean_word in name_map:
            target_ticker = name_map[clean_word]
            break

    if not target_ticker:
        matches = re.findall(r'\b[A-Z]{2,5}\b', user_text.upper())
        ignore = {"WHAT", "PRICE", "STOCK", "TELL", "WITH", "THIS", "FROM", "ABOUT"}
        valid = [m for m in matches if m not in ignore]
        if valid:
            target_ticker = valid[0]

    # Fetch live stock quote via Finnhub API
    market_context = ""
    if target_ticker:
        market_context = await fetch_finnhub_quote(target_ticker)

    # Context construction
    profile = user_profiles.get(chat_id, {})
    user_role = profile.get("role", "Finance Professional")
    watchlist = profile.get("watchlist", [])

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User Role: {user_role}\n"
        f"User Watchlist: {', '.join(watchlist)}\n"
        f"Live Market Context:\n{market_context if market_context else 'No live feed available for this query.'}"
    )

    # Groq Llama 3.3 Inference
    try:
        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": context_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.1
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Analysis Error: {str(e)}"

    await send_message(chat_id, reply)

# ==========================================
# FASTAPI ENDPOINTS
# ==========================================

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Telegram Financial AI Bot is live on Railway"}

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text")
    voice = message.get("voice")

    if chat_id:
        if voice:
            voice_file_id = voice.get("file_id")
            background_tasks.add_task(
                process_and_reply, 
                chat_id=chat_id, 
                voice_file_id=voice_file_id
            )
        elif user_text:
            background_tasks.add_task(
                process_and_reply, 
                chat_id=chat_id, 
                user_text=user_text
            )

    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
