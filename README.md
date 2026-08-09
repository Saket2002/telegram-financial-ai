# telegram-financial-ai
Autonomous Telegram Financial Analyst bot built with FastAPI, LangGraph, and multi-modal AI models for real-time market insights.

# 📈 Executive AI Financial Analyst for Telegram

An intelligent, multimodal Telegram bot that delivers real-time financial intelligence, equity research, and live market data directly to investment professionals, founders, and analysts. 

Powered by **Groq Llama 3.3**, **Groq Whisper**, **Finnhub API**, **FastAPI**, and **PostgreSQL**.

---

## 🚀 Features

* **💬 Conversational Onboarding:** Seamlessly captures professional roles and custom watchlists (e.g., `NVDA`, `AAPL`, `NIFTY 50`) without requiring rigid slash commands or menus.
* **📊 Live Stock & Index Data:** Fetches real-time equity prices via Finnhub and major global/Indian index levels (`NIFTY 50`, `SENSEX`, `BANKNIFTY`) via Yahoo Finance direct chart endpoints.
* **🎙️ Multimodal Voice Input:** Transcribes `.ogg` voice notes in real time using Groq Whisper (`whisper-large-v3-turbo`) and routes transcribed queries directly to the financial AI engine.
* **🗄️ Persistent Session Memory:** Uses PostgreSQL and SQLAlchemy ORM to securely retain user profiles, watchlists, and conversation history across server restarts.
* **📝 Executive Briefings:** Generates clean, formatted Telegram Markdown responses structured for rapid reading and actionable insight.

---

## 🛠️ Tech Stack

* **Backend Framework:** Python 3.11 / FastAPI / Uvicorn
* **AI & LLM Engine:** Groq API (`llama-3.3-70b-versatile`)
* **Voice Transcription:** Groq Whisper (`whisper-large-v3-turbo`)
* **Database & ORM:** PostgreSQL & SQLAlchemy ORM
* **Market Data APIs:** Finnhub API (Equities) & Yahoo Finance Chart API (Indices)
* **Hosting & Deployment:** Railway (FastAPI Web Service + Cloud PostgreSQL Database)

---

## 📋 Environment Variables

To run or deploy this project, configure the following environment variables on your server or in a `.env` file:

```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GROQ_API_KEY="your_groq_api_key"
FINNHUB_API_KEY="your_finnhub_api_key"
DATABASE_URL="postgresql://user:password@host:port/dbname"
