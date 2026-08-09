import os
import uvicorn
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI

app = FastAPI()

# Retrieve variables from Railway Environment
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Initialize Client using Groq's OpenAI-compatible endpoint
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

@app.get("/")
def read_root():
    """Health check endpoint for Railway"""
    return {"status": "ok", "message": "Telegram Financial AI Bot is live on Railway"}

async def process_and_reply(chat_id: int, user_text: str):
    if not client:
        reply = "Error: GROQ_API_KEY variable is missing on Railway."
    else:
        try:
            # Query Groq API using Llama 3.3 70B
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

    # Send message back to Telegram
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

if __name__ == "__main__":
    # Railway automatically injects the PORT environment variable
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
