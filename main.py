import os
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from google import genai
from google.genai import types

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

async def download_file(file_id: str) -> bytes:
    """Downloads voice notes or photos directly from Telegram servers."""
    async with httpx.AsyncClient() as http_client:
        res = await http_client.get(f"{TELEGRAM_API_URL}/getFile?file_id={file_id}")
        file_path = res.json()["result"]["file_path"]
        file_res = await http_client.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}")
        return file_res.content

async def process_and_reply(chat_id: int, user_text: str = None, voice_id: str = None, photo_id: str = None):
    if not client:
        reply = "Error: GEMINI_API_KEY environment variable is missing."
    else:
        try:
            contents = []
            system_instruction = (
                "You are an executive AI Financial Analyst inside Telegram. "
                "Provide concise, practical, and highly relevant financial insights. "
                "Do not use overly long generic introductory text."
            )

            # Process Voice Input
            if voice_id:
                audio_bytes = await download_file(voice_id)
                audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")
                contents.append(audio_part)
                contents.append("Transcribe this financial audio query and provide a clear, concise answer.")

            # Process Photo/Chart Input
            elif photo_id:
                image_bytes = await download_file(photo_id)
                image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                contents.append(image_part)
                prompt = user_text if user_text else "Analyze this financial document, table, or chart and summarize key takeaways."
                contents.append(prompt)

            # Process Text Input
            elif user_text:
                contents.append(user_text)

            # Generate AI response
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=system_instruction)
            )
            reply = response.text

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
    
    if not chat_id:
        return {"status": "ok"}

    user_text = message.get("text")
    voice = message.get("voice")
    photo = message.get("photo")

    voice_id = voice.get("file_id") if voice else None
    photo_id = photo[-1].get("file_id") if photo else None  # Select highest resolution
    caption = message.get("caption")

    if user_text or voice_id or photo_id:
        background_tasks.add_task(
            process_and_reply, 
            chat_id=chat_id, 
            user_text=caption or user_text, 
            voice_id=voice_id, 
            photo_id=photo_id
        )

    return {"status": "ok"}
