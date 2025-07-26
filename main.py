# full_bot.py
import logging
import random
import re
import string
import time
from datetime import datetime, timedelta

from flask import Flask, request
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, Update)
from telegram.constants import ChatAction
from telegram.ext import (Application, CallbackContext, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler,
                          filters)

# === CONFIGURATION ===
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
BOT_USERNAME = "secretmeet_bot"
WEBHOOK_URL = "https://secretmeet-bot.onrender.com"
PORT = 10000

# === FLASK APP ===
flask_app = Flask(__name__)

# === BOT STATE ===
users = {}
waiting_users = []
active_chats = {}
referrals = {}
referral_unlocked = {}
last_referral_time = {}
secret_rooms = {}
user_profiles = {}
feedback = {}
personality_tags = {}

popular_countries = ["Spain", "Saudi Arabia", "UAE", "Iran", "Iraq",
                     "Thailand", "Vietnam", "Philippines", "Nigeria",
                     "South Africa", "Kenya", "Colombia", "Argentina"]

GENDER_OPTIONS = ["Male", "Female"]
AGE_RANGE = list(range(14, 51))

# === UTILITIES ===
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def send_typing(context: CallbackContext, chat_id):
    context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    time.sleep(1.5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {}

    keyboard = [[InlineKeyboardButton(country, callback_data=f"country_{country}")]
                for country in popular_countries[:5]]
    keyboard.append([InlineKeyboardButton("More", callback_data="country_more")])

    await update.message.reply_text("🌍 Choose your country:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("country_"):
        country = query.data.split("_")[1]
        users[user_id]["country"] = country
        await send_age_selection(query, user_id)

    elif query.data.startswith("age_"):
        age = int(query.data.split("_")[1])
        users[user_id]["age"] = age
        await send_gender_selection(query, user_id)

    elif query.data in GENDER_OPTIONS:
        users[user_id]["gender"] = query.data
        await query.message.reply_text("✅ Setup complete!",
            reply_markup=ReplyKeyboardMarkup([
                ["🔍 Find a Partner"],
                ["🎯 Search by Gender"]
            ], resize_keyboard=True))

    elif query.data == "country_more":
        keyboard = [[InlineKeyboardButton(c, callback_data=f"country_{c}")]
                    for c in popular_countries[5:]]
        await query.message.edit_text("🌍 Choose your country:",
                                      reply_markup=InlineKeyboardMarkup(keyboard))

def create_paginated_keyboard(options, prefix, per_page=8):
    keyboard = []
    for i in range(0, len(options), per_page):
        page = options[i:i + per_page]
        row = [InlineKeyboardButton(str(opt), callback_data=f"{prefix}_{opt}") for opt in page]
        keyboard.append(row)
    return keyboard

async def send_age_selection(query, user_id):
    keyboard = create_paginated_keyboard(AGE_RANGE, "age", per_page=6)
    await query.message.reply_text("🎂 Select your age:",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def send_gender_selection(query, user_id):
    keyboard = [[InlineKeyboardButton("Male", callback_data="Male"),
                 InlineKeyboardButton("Female", callback_data="Female")]]
    await query.message.reply_text("🚻 Select your gender:",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        await update.message.reply_text("❗You're already in a chat.")
        return
    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id

        await context.bot.send_message(partner_id, "✅ You’re now connected! Say hi!")
        await context.bot.send_message(user_id, "✅ You’re now connected! Say hi!")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⏳ Waiting for a partner...")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in active_chats:
        await update.message.reply_text("❗You are not in a chat.")
        return

    partner_id = active_chats.pop(user_id)
    active_chats.pop(partner_id, None)

    await context.bot.send_message(partner_id, "❗Your partner has left the chat.")
    await context.bot.send_message(user_id, "❌ You have left the chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        send_typing(context, partner_id)
        await context.bot.send_message(partner_id, update.message.text)
    else:
        await update.message.reply_text("❗You're not connected. Press 🔍 Find a Partner")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Setup your profile\n"
        "/connect - Find a chat partner\n"
        "/disconnect - Leave current chat\n"
        "/referral - Invite & unlock features\n"
        "/profile - View or edit your info\n"
        "/help - Show this help menu"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = users.get(user_id, {})
    await update.message.reply_text(
        f"🌍 Country: {data.get('country', '-') }\n"
        f"🎂 Age: {data.get('age', '-') }\n"
        f"🚻 Gender: {data.get('gender', '-') }"
    )

# === FLASK ROUTES ===
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok"

@flask_app.route("/")
def index():
    return "Bot is live!"

# === MAIN ===
logging.basicConfig(level=logging.INFO)
application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("connect", connect))
application.add_handler(CommandHandler("disconnect", disconnect))
application.add_handler(CommandHandler("profile", profile))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

application.bot.set_my_commands([
    BotCommand("start", "Start the bot"),
    BotCommand("connect", "Find a partner"),
    BotCommand("disconnect", "Leave chat"),
    BotCommand("profile", "Show your profile"),
    BotCommand("help", "Help menu")
])

application.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path=BOT_TOKEN,
    webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    allowed_updates=Update.ALL_TYPES,
    flask_app=flask_app
