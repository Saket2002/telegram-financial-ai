import os
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Initialize Client using Groq's OpenAI-compatible base URL
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

async def process_and_reply(chat_id: int, user_text: str):
    if not client:
        reply = "Error: GROQ_API_KEY environment variable is missing on Render."
    else:
        try:
            # Generate AI response using Llama 3.3 70B on Groq
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an executive AI Financial Analyst inside Telegram. Provide concise, practical, and actionable financial insights."
                    },
                    {
                        "role": "user",
                        "content": user_text
                    }
                ]
            )
            reply = response.choices[0].message.content

        except Exception as e:
            reply = f"Error processing request: {str(e)}"

    # Send response back to Telegram
    async with httpx.AsyncClient() as http_client:
        await http_client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": reply}
        )

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
