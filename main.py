import random
import string
import time
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)
import asyncio

# ====== CONFIGURATION ======
TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== STATE VARIABLES ======
user_data = {}
waiting_users = []
chat_pairs = {}
referrals = defaultdict(set)
referral_time = {}
gender_unlock = {}
secret_rooms = {}
personalities = {}
confessions = {}
feedback_data = {}

# ====== STATIC DATA ======
COUNTRIES = [
    "India", "USA", "UK", "Canada", "Australia", "Germany", "France",
    "Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand",
    "Vietnam", "Philippines", "Nigeria", "South Africa", "Kenya",
    "Colombia", "Argentina"
]
AGES = [str(i) for i in range(14, 51)]
GENDERS = ["Male", "Female"]
ICEBREAKERS = [
    "What's your favorite way to spend a weekend?",
    "If you could travel anywhere right now, where would you go?",
    "What’s a fun fact about you most people don’t know?",
    "What’s your favorite movie or show recently?"
]
PERSONALITY_TAGS = ["Funny", "Deep Thinker", "Adventurous", "Introvert", "Extrovert"]

# ====== PAGINATION UTIL ======
def paginate_buttons(items, prefix, per_page=5):
    pages = [items[i:i + per_page] for i in range(0, len(items), per_page)]
    keyboards = []
    for i, page in enumerate(pages):
        btns = [InlineKeyboardButton(text=item, callback_data=f"{prefix}:{item}") for item in page]
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"{prefix}_page:{i-1}"))
        if i < len(pages) - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"{prefix}_page:{i+1}"))
        keyboards.append(btns + nav)
    return keyboards

# ====== HANDLERS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    context.user_data['page'] = 0
    pages = paginate_buttons(COUNTRIES, "country")
    keyboard = [pages[0]]
    await update.message.reply_text(
        "🌍 Select your country:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data.startswith("country_page"):
        page = int(query.data.split(":")[1])
        context.user_data['page'] = page
        keyboard = [paginate_buttons(COUNTRIES, "country")[page]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("country:"):
        country = query.data.split(":")[1]
        user_data[user_id]['country'] = country
        pages = paginate_buttons(AGES, "age")
        context.user_data['page'] = 0
        await query.edit_message_text(
            "🎂 Select your age:",
            reply_markup=InlineKeyboardMarkup([pages[0]])
        )

async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data.startswith("age_page"):
        page = int(query.data.split(":")[1])
        context.user_data['page'] = page
        keyboard = [paginate_buttons(AGES, "age")[page]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("age:"):
        age = query.data.split(":")[1]
        user_data[user_id]['age'] = age
        keyboard = [[
            InlineKeyboardButton("♂️ Male", callback_data="gender:Male"),
            InlineKeyboardButton("♀️ Female", callback_data="gender:Female")
        ]]
        await query.edit_message_text("👤 Select your gender:", reply_markup=InlineKeyboardMarkup(keyboard))

async def gender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    gender = query.data.split(":")[1]
    user_data[user_id]['gender'] = gender
    user_data[user_id]['setup_complete'] = True

    keyboard = [[
        KeyboardButton("🔍 Find a Partner")
    ]]
    await query.edit_message_text("✅ Setup Complete! Use the button below to start chatting.")
    await context.bot.send_message(
        chat_id=user_id,
        text="Choose an option:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ====== FLASK KEEP ALIVE ======
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ====== MAIN ======
if __name__ == '__main__':
    keep_alive()
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(country_handler, pattern="^country"))
    application.add_handler(CallbackQueryHandler(age_handler, pattern="^age"))
    application.add_handler(CallbackQueryHandler(gender_handler, pattern="^gender"))
    application.run_polling()
