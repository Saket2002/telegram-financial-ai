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

user_profiles = {}

SYSTEM_PROMPT = """
You are an executive AI Financial Analyst inside Telegram.
You provide precise, real-time financial intelligence to save users time.

Rules:
1. Always use the provided Live Market Context for prices, market caps, and ratios.
2. NEVER mention knowledge cutoffs or tell users to check external websites.
3. Keep responses concise, structured, and easy to read using bold Markdown.
4. Do not use slash commands or menu language—be completely conversational.
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

async def fetch_stock_data_api(symbol: str) -> str:
    """Direct Yahoo Finance API fetch bypassing scraper blocks"""
    symbol = symbol.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        async with httpx.AsyncClient() as client_http:
            res = await client_http.get(url, headers=headers, timeout=5.0)
            if res.status_code == 200:
                meta = res.json()["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                currency = meta.get("currency", "USD")
                prev_close = meta.get("chartPreviousClose")
                change_pct = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0
                
                return (
                    f"LIVE MARKET DATA FOR {symbol}:\n"
                    f"- Current Price: ${price} {currency}\n"
                    f"- Daily Change: {change_pct}%\n"
                    f"- Previous Close: ${prev_close}"
                )
    except Exception:
        pass
    return ""

async def handle_onboarding(chat_id: int, user_text: str) -> bool:
    profile = user_profiles.get(chat_id, {"step": 0, "role": None, "watchlist": []})
    
    if profile["step"] == 0:
        greeting = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor research and market briefings to your workflow, "
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
        profile["step"] = 3
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
    # Check if user needs onboarding
    if chat_id not in user_profiles or user_profiles[chat_id]["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "start", "/start"]:
            user_profiles[chat_id] = {"step": 0, "role": None, "watchlist": []}
        if await handle_onboarding(chat_id, user_text):
            return

    # Extract ticker candidates from message
    words = [w.strip("?,.!") for w in user_text.upper().split()]
    market_context = ""
    
    # Common financial tickers map
    known_tickers = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "AMD", "INTC"]
    
    for word in words:
        if word in known_tickers or (len(word) <= 5 and word.isalpha()):
            stock_info = await fetch_stock_data_api(word)
            if stock_info:
                market_context += f"\n{stock_info}"
                break

    profile = user_profiles.get(chat_id, {})
    user_role = profile.get("role", "Finance Professional")
    watchlist = profile.get("watchlist", [])

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User Role: {user_role}\n"
        f"User Watchlist: {', '.join(watchlist)}\n"
        f"Live Market Context: {market_context if market_context else 'No live feed available for this query.'}"
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
