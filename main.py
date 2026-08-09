import os
import uvicorn
import httpx
import yfinance as yf
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

# Memory store for user onboarding and watchlists
user_profiles = {}

SYSTEM_PROMPT = """
You are an executive AI Financial Analyst inside Telegram.
Your goal is to save the user time by providing concise, actionable financial intelligence.

Rules:
1. Speak concisely like a senior equity research analyst.
2. Focus on WHY metrics move and WHAT matters for financial decisions.
3. Use clean Telegram Markdown (bold metrics, bullet points).
4. Do NOT use command language, slash commands, or menus. Keep interactions completely conversational.
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

def fetch_stock_data(ticker_symbol: str) -> str:
    """Helper to pull real-time stock info via yfinance"""
    try:
        ticker = yf.Ticker(ticker_symbol.strip().upper())
        info = ticker.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        currency = info.get("currency", "USD")
        name = info.get("shortName", ticker_symbol)
        pe_ratio = info.get("forwardPE", "N/A")
        market_cap = info.get("marketCap", "N/A")
        
        if price:
            return f"Live Market Data for {name} ({ticker_symbol.upper()}): Current Price = {price} {currency}, Forward P/E = {pe_ratio}, Market Cap = {market_cap}."
    except Exception:
        pass
    return ""

async def handle_onboarding(chat_id: int, user_text: str) -> bool:
    profile = user_profiles.get(chat_id, {"step": 0, "role": None, "watchlist": []})
    
    if profile["step"] == 0:
        greeting = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor research and briefings to your workflow, "
            "**what best describes your role?** (e.g., *Investor, Equity Analyst, Founder, Finance Student, or VP of Finance*)"
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

async def process_and_reply(chat_id: int, user_text: str):
    # Trigger onboarding if new user or on explicit restart
    if chat_id not in user_profiles or user_profiles[chat_id]["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "start", "/start"]:
            user_profiles[chat_id] = {"step": 0, "role": None, "watchlist": []}
        if await handle_onboarding(chat_id, user_text):
            return

    # Normal AI Analysis Flow
    profile = user_profiles.get(chat_id, {})
    user_role = profile.get("role", "Finance Professional")
    watchlist = profile.get("watchlist", [])
    
    # Check if user mentioned a ticker in their message to fetch live data
    market_context = ""
    for token in user_text.replace("?", "").split():
        if len(token) <= 5 and token.isalpha():
            data = fetch_stock_data(token)
            if data:
                market_context += f"\n{data}"
                break

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User Profile: Role = {user_role}, Saved Watchlist = {', '.join(watchlist)}.\n"
        f"Live Market Context: {market_context}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": context_prompt},
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
