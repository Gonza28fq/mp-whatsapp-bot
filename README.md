# 🤖 WhatsApp Payment Verification Bot

A WhatsApp bot that allows business employees to verify in real-time whether a Mercado Pago transfer has been credited to the account — without needing to call or disturb the business owner.

## 🎯 How it works

```
Customer makes a transfer
        ↓
Employee sends a WhatsApp message to the bot
        ↓
Bot queries the Mercado Pago API
        ↓
Bot replies instantly to the employee ✅ or ❌
```

## ✨ Features

- **Real-time payment verification** — responds in under 3 seconds
- **Multiple query formats** — by amount, general inquiry, or list recent payments
- **Argentine timezone** — all times displayed in UTC-3
- **Smart amount matching** — 2% tolerance for rounding differences
- **Authorized numbers whitelist** — only approved employees can use the bot
- **Multi-channel support** — works with Twilio Sandbox and Meta WhatsApp Business API
- **24/7 availability** — deployed on Railway

## 💬 Supported commands

| Employee writes | Bot does |
|---|---|
| `5000` | Searches for a $5,000 payment in the last 20 minutes |
| `$5.000` | Same as above with Argentine number format |
| `5000 hace 5` | Searches for that amount in the last 5 minutes |
| `impactó?` / `entró algo?` | Returns the most recent payment |
| `se acreditó?` / `entró plata?` | General payment inquiry |
| `últimos pagos` | Lists the last 5 payments |
| `últimos 3 pagos` | Lists the last 3 payments (1-10) |

## 🚀 Getting started

### Prerequisites

- Python 3.12+
- Mercado Pago account with API access
- Twilio account (Sandbox) or Meta WhatsApp Business API
- Railway account for deployment

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/mp-whatsapp-bot.git
cd mp-whatsapp-bot

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
```

### Environment variables

```env
# Mercado Pago
MP_ACCESS_TOKEN=APP_USR-xxxxxxxxxxxxxxxxxxxx

# Meta WhatsApp Business API
WHATSAPP_TOKEN=EAAxxxxxxxxxxxxxxxx
WHATSAPP_PHONE_ID=1234567890
WEBHOOK_VERIFY_TOKEN=your_secret_token_here

# Authorized phone numbers (comma-separated, no + prefix)
NUMEROS_AUTORIZADOS=5493815958981,5493816123456

# Server
PORT=8000
```

### Running locally

```bash
python run.py
```

Server starts at `http://localhost:8000`

### Expose locally with ngrok (for webhook testing)

```bash
ngrok http 8000
```

Use the generated URL as your webhook in Twilio or Meta.

## 📁 Project structure

```
mp-whatsapp-bot/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + webhook handler
│   ├── mercadopago.py   # Mercado Pago API integration
│   └── parser.py        # Message parser
├── tests/
│   └── test_parser.py   # Unit tests
├── run.py               # Entry point
├── requirements.txt
├── railway.toml         # Railway deployment config
├── Procfile
└── .env.example
```

## 🔌 Webhook endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/webhook` | Meta webhook verification |
| `POST` | `/webhook` | Receives incoming WhatsApp messages |

## 🔒 Security

- **Whitelist**: Only authorized phone numbers can interact with the bot. Set `NUMEROS_AUTORIZADOS` in environment variables. If left empty, all numbers are allowed (useful for testing).
- **Read-only**: The Mercado Pago token only has read permissions — it cannot move funds.
- **Secrets**: All credentials are stored as environment variables, never hardcoded.

## 🌐 Deployment on Railway

1. Push code to GitHub
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repository
4. Add environment variables in the **Variables** tab
5. Railway auto-deploys on every push to `main`

## 📦 Running tests

```bash
pytest tests/ -v
```

## 🔄 Switching between Twilio and Meta

The bot currently supports both providers. The `main.py` file contains the Meta WhatsApp Business API integration. For Twilio Sandbox testing, refer to the `railway.toml` and webhook configuration.

### Meta WhatsApp Business API setup

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create a **Business** app
3. Add the **WhatsApp** product
4. Register your phone number
5. Copy `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_ID` to your environment variables
6. Set webhook URL to: `https://your-railway-url.up.railway.app/webhook`
7. Set verify token to match your `WEBHOOK_VERIFY_TOKEN`

### Twilio Sandbox setup

1. Create account at [twilio.com](https://twilio.com)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Join the sandbox by sending `join <code>` to the Twilio number
4. Set webhook URL in **Sandbox Settings**

## 🛠️ Tech stack

| Component | Technology |
|---|---|
| Backend | Python + FastAPI |
| HTTP client | httpx (async) |
| Hosting | Railway |
| Messaging | Meta WhatsApp Business API / Twilio |
| Payment data | Mercado Pago API |

## 📄 License

This project is proprietary software. All rights reserved.
