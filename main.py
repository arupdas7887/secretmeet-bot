from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    CallbackQueryHandler, filters
)
import os
import logging
import datetime

# === CONFIG ===
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
WEBHOOK_URL = "https://secretmeet-bot.onrender.com"
PORT = int(os.environ.get("PORT", 10000))

# === SETUP ===
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
bot_app = Application.builder().token(BOT_TOKEN).build()

# === USER DATA ===
users = {}
waiting_users = []
chat_pairs = {}

# === HELPER FUNCTIONS ===
def get_user_info(user_id):
    return users.get(user_id, {})

def find_partner(user_id):
    for uid in waiting_users:
        if uid != user_id:
            return uid
    return None

def end_chat(user_id):
    partner_id = chat_pairs.pop(user_id, None)
    if partner_id:
        chat_pairs.pop(partner_id, None)
        return partner_id
    return None

def is_referral_unlocked(user_id):
    return users.get(user_id, {}).get("referral_unlocked", False)

# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {"step": "country"}

    countries = ["Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand", "Vietnam", "Philippines", "Nigeria", "South Africa", "Kenya", "Colombia", "Argentina"]
    keyboard = [[InlineKeyboardButton(c, callback_data=f"country_{c}")] for c in countries]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🌍 Select your country:", reply_markup=reply_markup)

# === CALLBACKS ===
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    data = query.data
    step = users.get(user_id, {}).get("step")

    if data.startswith("country_"):
        country = data.split("_", 1)[1]
        users[user_id]["country"] = country
        users[user_id]["step"] = "age"

        age_buttons = [[InlineKeyboardButton(str(i), callback_data=f"age_{i}")] for i in range(14, 51)]
        age_markup = InlineKeyboardMarkup(age_buttons[:10])  # First page only for simplicity
        await query.edit_message_text("🎂 Select your age:", reply_markup=age_markup)

    elif data.startswith("age_"):
        age = data.split("_", 1)[1]
        users[user_id]["age"] = age
        users[user_id]["step"] = "gender"

        gender_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("♂️ Male", callback_data="gender_male"), InlineKeyboardButton("♀️ Female", callback_data="gender_female")]
        ])
        await query.edit_message_text("🚻 Select your gender:", reply_markup=gender_markup)

    elif data.startswith("gender_"):
        gender = data.split("_", 1)[1]
        users[user_id]["gender"] = gender
        users[user_id]["step"] = "done"

        keyboard = [[
            InlineKeyboardButton("🔍 Find a Partner", callback_data="find_partner")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✅ Setup complete. Ready to chat!", reply_markup=reply_markup)

    elif data == "find_partner":
        if user_id in chat_pairs:
            await query.edit_message_text("You're already in a chat.")
            return

        partner = find_partner(user_id)
        if partner:
            chat_pairs[user_id] = partner
            chat_pairs[partner] = user_id
            waiting_users.remove(partner)

            await context.bot.send_message(chat_id=user_id, text="🤝 Connected! Say hi!")
            await context.bot.send_message(chat_id=partner, text="🤝 Connected! Say hi!")
        else:
            waiting_users.append(user_id)
            await query.edit_message_text("⏳ Waiting for a partner...")

# === MESSAGE HANDLER ===
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = chat_pairs.get(user_id)

    if partner_id:
        await context.bot.send_chat_action(partner_id, action="typing")
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)
    else:
        await update.message.reply_text("❗You're not in a chat. Use /connect to find a partner.")

# === CONNECT ===
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Connecting you... Please wait.")
    await handle_callback(update, context)

# === DISCONNECT ===
async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = end_chat(user_id)

    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="❗Your partner has left the chat.")
        await update.message.reply_text("🚫 You left the chat.")
    else:
        await update.message.reply_text("ℹ️ You're not in any chat.")

# === HELP ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 *SecretMeet Bot Commands:*
/start – Setup your profile
/connect – Find a partner
/disconnect – Leave chat
/help – Show help
""", parse_mode="Markdown")

# === FLASK WEBHOOK ===
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put(update)
    return "OK"

@app.route("/")
def index():
    return "Bot is live!"

# === RUN ===
async def set_webhook():
    await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("connect", connect))
bot_app.add_handler(CommandHandler("disconnect", disconnect))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(CallbackQueryHandler(handle_callback))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

if __name__ == '__main__':
    import asyncio
    asyncio.run(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
