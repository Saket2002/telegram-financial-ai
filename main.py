import os
import uvicorn
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI
from groq import Groq

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Initialize Groq Client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Initialize OpenAI Client pointing to Groq for Chat Completions
openai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None


async def send_telegram_message(chat_id: int, text: str):
    """Utility to send markdown messages to Telegram"""
    async with httpx.AsyncClient() as http_client:
        await http_client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
        )


async def transcribe_telegram_voice(file_id: str) -> str:
    """Fetches Telegram voice file URL, downloads .ogg bytes, and transcribes via Groq Whisper"""
    if not groq_client:
        return ""

    async with httpx.AsyncClient() as http_client:
        # 1. Get file path from Telegram API
        file_info_res = await http_client.get(
            f"{TELEGRAM_API_URL}/getFile",
            params={"file_id": file_id}
        )
        if file_info_res.status_code != 200:
            return ""

        file_path = file_info_res.json()["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

        # 2. Download the voice audio file (.ogg format)
        audio_res = await http_client.get(download_url)
        if audio_res.status_code != 200:
            return ""

        audio_bytes = audio_res.content

    # 3. Send audio bytes to Groq Whisper endpoint
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


async def process_and_reply(chat_id: int, user_text: str = None, voice_file_id: str = None):
    # If a voice message was received, transcribe it first
    if voice_file_id and not user_text:
        await send_telegram_message(chat_id, "🎙️ *Transcribing voice message...*")
        user_text = await transcribe_telegram_voice(voice_file_id)

        if not user_text.strip():
            await send_telegram_message(chat_id, "Sorry, I couldn't understand that voice message. Please try speaking clearer or send text.")
            return

        # Notify the user what was transcribed
        await send_telegram_message(chat_id, f"📝 *Transcription:* \"{user_text}\"")

    if not user_text:
        return

    # Process transcribed user text with Groq Llama 3.3
    try:
        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an executive AI Financial Analyst inside Telegram. Provide concise, practical, and actionable insights."
                },
                {"role": "user", "content": user_text}
            ],
            temperature=0.2
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Analysis Error: {str(e)}"

    await send_telegram_message(chat_id, reply)


@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text")
    voice = message.get("voice")

    if chat_id:
        if voice:
            # Handle voice note
            voice_file_id = voice.get("file_id")
            background_tasks.add_task(
                process_and_reply,
                chat_id=chat_id,
                voice_file_id=voice_file_id
            )
        elif user_text:
            # Handle standard text input
            background_tasks.add_task(
                process_and_reply,
                chat_id=chat_id,
                user_text=user_text
            )

    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
