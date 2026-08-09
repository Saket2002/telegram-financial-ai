import os
import re
import uvicorn
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI
from groq import Groq

from database import (
    init_db, 
    get_user_profile_db, 
    update_user_profile_db, 
    log_chat_history
)

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
openai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
You are an executive AI Financial Analyst inside Telegram.
Your primary job is delivering live, actionable financial intelligence concisely to save users time.

CRITICAL INSTRUCTIONS:
1. Always prioritize the provided 'Live Market Context' for current stock prices, index levels, and valuation metrics.
2. NEVER mention knowledge cutoffs, training dates, or tell the user to check external websites.
3. Use clean Telegram Markdown formatting (bold key figures, clear bullet points).
4. Keep all interactions conversational and executive—avoid slash commands or menu language.
"""

@app.on_event("startup")
def startup_event():
    init_db()

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

async def fetch_index_quote(query_text: str) -> str:
    index_map = {
        "NSEI": ("NIFTY 50", "^NSEI"),
        "^NSEI": ("NIFTY 50", "^NSEI"),
        "NIFTY": ("NIFTY 50", "^NSEI"),
        "NIFTY50": ("NIFTY 50", "^NSEI"),
        "BANKNIFTY": ("BANK NIFTY", "^NSEBANK"),
        "SENSEX": ("BSE SENSEX", "^BSESN"),
        "BSESN": ("BSE SENSEX", "^BSESN"),
        "SP500": ("S&P 500", "^GSPC"),
        "NASDAQ": ("NASDAQ Composite", "^IXIC")
    }

    matched_key = None
    clean_words = [re.sub(r'[^A-Z0-9^]', '', w) for w in query_text.upper().split()]
    for word in clean_words:
        if word in index_map:
            matched_key = word
            break

    if not matched_key:
        return ""

    display_name, symbol = index_map[matched_key]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        async with httpx.AsyncClient() as client_http:
            res = await client_http.get(url, headers=headers, timeout=5.0)
            if res.status_code == 200:
                meta = res.json()["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                currency = meta.get("currency", "INR")
                prev_close = meta.get("chartPreviousClose")
                change_pct = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0

                return (
                    f"REAL-TIME MARKET DATA FOR {display_name} ({symbol}):\n"
                    f"- Current Index Level: {price:,.2f} {currency}\n"
                    f"- Daily Change: {change_pct}%\n"
                    f"- Previous Close: {prev_close:,.2f} {currency}"
                )
    except Exception as e:
        print(f"Index fetch error for {symbol}: {e}")
    return ""

async def fetch_finnhub_quote(symbol: str) -> str:
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
        print(f"Finnhub error for {symbol}: {e}")
    return ""

async def handle_onboarding(chat_id: int, user_text: str) -> bool:
    profile = get_user_profile_db(chat_id)
    text_upper = user_text.upper()

    financial_keywords = ["PRICE", "STOCK", "NVDA", "AAPL", "MSFT", "NIFTY", "NSEI", "SENSEX", "VALUATION", "MARKET"]
    if any(keyword in text_upper for keyword in financial_keywords) and profile["step"] in [1, 2]:
        update_user_profile_db(chat_id, step=3, role="Finance Professional", watchlist=["NVDA", "AAPL", "NIFTY"])
        return False

    if profile["step"] == 0:
        greeting = (
            "Welcome! I am your personal AI Financial Analyst.\n\n"
            "To help me tailor research and briefings to your workflow, "
            "**what best describes your role?** (e.g., *Investor, Equity Analyst, Founder, VP of Finance*)"
        )
        update_user_profile_db(chat_id, step=1)
        await send_message(chat_id, greeting)
        return True

    elif profile["step"] == 1:
        role_text = user_text.strip()
        update_user_profile_db(chat_id, step=2, role=role_text)

        reply = (
            f"Got it—customizing intelligence for a **{role_text}**.\n\n"
            "Which key companies, tickers, or sectors do you follow most closely? "
            "(e.g., *Nvidia, Apple, NIFTY 50, TSLA*)"
        )
        await send_message(chat_id, reply)
        return True

    elif profile["step"] == 2:
        watchlist_items = [item.strip().upper() for item in user_text.split(",")]
        update_user_profile_db(chat_id, step=3, watchlist=watchlist_items)

        confirmation = (
            f"Perfect. I've configured your focus areas: **{', '.join(watchlist_items)}**.\n\n"
            "I will tailor all financial research, metric comparisons, and briefings to these priorities. "
            "How can I assist your workflow right now?"
        )
        await send_message(chat_id, confirmation)
        return True

    return False

async def process_and_reply(chat_id: int, user_text: str = None):
    if not user_text:
        return

    profile = get_user_profile_db(chat_id)

    if profile["step"] < 3:
        if user_text.lower().strip() in ["hello", "hi", "start", "/start"]:
            update_user_profile_db(chat_id, step=0)
        if await handle_onboarding(chat_id, user_text):
            return

    market_context = await fetch_index_quote(user_text)

    if not market_context:
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

        if target_ticker:
            market_context = await fetch_finnhub_quote(target_ticker)

    profile = get_user_profile_db(chat_id)
    user_role = profile["role"] if profile["role"] else "Finance Professional"
    watchlist = profile["watchlist"] if profile["watchlist"] else []

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User Role: {user_role}\n"
        f"User Watchlist: {', '.join(watchlist)}\n"
        f"Live Market Context:\n{market_context if market_context else 'No live feed available for this query.'}"
    )

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

    log_chat_history(chat_id, user_text, reply)
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
