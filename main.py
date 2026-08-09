import os
import re
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
Your core priority is providing precise, real-time market data to save users time.

RULES:
1. Always use the provided 'Live Market Context' for current stock prices and valuations.
2. NEVER mention knowledge cutoffs, training dates, or tell the user to check external websites.
3. Format output cleanly in Telegram Markdown with bold key numbers.
4. Keep answers concise, direct, and conversational.
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

async def fetch_live_quote(symbol: str) -> str:
    """Fetches real-time price using Yahoo Finance mobile quote endpoint"""
    symbol = symbol.strip().upper()
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=price,summaryDetail,defaultKeyStatistics"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    }

    try:
        async with httpx.AsyncClient() as client_http:
            res = await client_http.get(url, headers=headers, timeout=6.0)
            if res.status_code == 200:
                data = res.json()["quoteSummary"]["result"][0]
                price_data = data.get("price", {})
                
                price = price_data.get("regularMarketPrice", {}).get("raw")
                currency = price_data.get("currency", "USD")
                change_pct = price_data.get("regularMarketChangePercent", {}).get("fmt", "0%")
                market_cap = price_data.get("marketCap", {}).get("fmt", "N/A")
                short_name = price_data.get("shortName", symbol)
                
                if price:
                    return (
                        f"LIVE REAL-TIME DATA FOR {short_name} ({symbol}):\n"
                        f"- Current Stock Price: ${price:.2f} {currency}\n"
                        f"- Today's Change: {change_pct}\n"
                        f"- Market Capitalization: {market_cap}"
                    )
    except Exception as e:
        print(f"Fetch error for {symbol}: {e}")

    return ""

async def handle_onboarding(chat_id: int, user_text: str) -> bool:
    profile = user_profiles.get(chat_id, {"step": 0, "role": None, "watchlist": []})
    
    if profile["step"] == 0:
        greeting = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor research and briefings to your daily workflow, "
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
    if chat_id not in user_profiles or user_profiles[chat_id]["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "start", "/start"]:
            user_profiles[chat_id] = {"step": 0, "role": None, "watchlist": []}
        if await handle_onboarding(chat_id, user_text):
            return

    # Match company names or stock symbols
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

    market_context = ""
    if target_ticker:
        market_context = await fetch_live_quote(target_ticker)

    profile = user_profiles.get(chat_id, {})
    user_role = profile.get("role", "Finance Professional")
    watchlist = profile.get("watchlist", [])

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User Role: {user_role}\n"
        f"User Watchlist: {', '.join(watchlist)}\n"
        f"Live Market Context:\n{market_context if market_context else 'No live API data available for this request.'}"
    )

    try:
        response = client.chat.completions.create(
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
