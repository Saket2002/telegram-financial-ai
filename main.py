import os
import httpx
from fastapi import FastAPI, Request, BackgroundTasks

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

async def send_telegram_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text", "")

    if chat_id and user_text:
        reply = f"Render Webhook Live! You said: '{user_text}'."
        background_tasks.add_task(send_telegram_message, chat_id, reply)

    return {"status": "ok"}
