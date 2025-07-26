import logging
import random
import string
import time
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask
from threading import Thread

from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, KeyboardButton)
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, CallbackContext, CallbackQueryHandler,
                          ConversationHandler, ContextTypes)

# ===== CONFIGURATION =====
TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
popular_countries = ["Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand",
                     "Vietnam", "Philippines", "Nigeria", "South Africa",
                     "Kenya", "Colombia", "Argentina"]
all_countries = popular_countries  # Add more if needed
ages = list(range(14, 51))

# ===== LOGGING =====
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== GLOBAL VARIABLES =====
users = {}
waiting_users = []
chats = {}
referrals = defaultdict(list)
gender_unlock = defaultdict(lambda: {"count": 0, "expires": None})
feedback = {}
rooms = {}
filtered_words = ["badword1", "badword2"]

# ===== FLASK FOR RENDER KEEP-ALIVE =====
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# ===== UTILITIES =====
def typing_action(context: CallbackContext, chat_id):
    context.bot.send_chat_action(chat_id=chat_id, action="typing")
    time.sleep(random.uniform(0.5, 1.5))

def paginate_buttons(items, prefix, per_page=6):
    pages = [items[i:i + per_page] for i in range(0, len(items), per_page)]
    keyboards = []
    for i, page in enumerate(pages):
        buttons = [InlineKeyboardButton(item, callback_data=f"{prefix}:{item}") for item in page]
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}_page:{i - 1}"))
        if i < len(pages) - 1:
            nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}_page:{i + 1}"))
        keyboards.append(buttons + nav)
    return keyboards

def build_keyboard(page_buttons):
    return InlineKeyboardMarkup([[btn] for btn in page_buttons])

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {}
    page_buttons = paginate_buttons(popular_countries, "country")
    await update.message.reply_text("🌍 Select your country:", reply_markup=build_keyboard(page_buttons[0]))
    context.user_data['page'] = page_buttons
    context.user_data['page_num'] = 0

def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data.startswith("country:"):
        country = data.split(":")[1]
        users[user_id]['country'] = country
        age_buttons = paginate_buttons([str(a) for a in ages], "age")
        context.user_data['age_pages'] = age_buttons
        context.user_data['age_page_num'] = 0
        return query.edit_message_text("🎂 Select your age:", reply_markup=build_keyboard(age_buttons[0]))

    elif data.startswith("age:"):
        age = int(data.split(":")[1])
        users[user_id]['age'] = age
        gender_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👦 Male", callback_data="gender:Male"),
             InlineKeyboardButton("👧 Female", callback_data="gender:Female")]
        ])
        return query.edit_message_text("🚻 Select your gender:", reply_markup=gender_kb)

    elif data.startswith("gender:"):
        gender = data.split(":")[1]
        users[user_id]['gender'] = gender
        kb = ReplyKeyboardMarkup([
            [KeyboardButton("🔍 Find a Partner")],
            [KeyboardButton("🎯 Search by Gender")]
        ], resize_keyboard=True)
        return query.edit_message_text("✅ Setup complete!", reply_markup=kb)

    elif data.startswith("country_page"):
        page = int(data.split(":")[1])
        pages = context.user_data['page']
        return query.edit_message_reply_markup(reply_markup=build_keyboard(pages[page]))

    elif data.startswith("age_page"):
        page = int(data.split(":")[1])
        pages = context.user_data['age_pages']
        return query.edit_message_reply_markup(reply_markup=build_keyboard(pages[page]))

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats:
        return await update.message.reply_text("You're already in a chat. Use /disconnect first.")

    for partner_id in waiting_users:
        if partner_id != user_id and partner_id not in chats:
            chats[user_id] = partner_id
            chats[partner_id] = user_id
            waiting_users.remove(partner_id)
            await context.bot.send_message(partner_id, "✅ Partner found! Say hi!")
            await context.bot.send_message(user_id, "✅ Partner found! Say hi!")
            return

    waiting_users.append(user_id)
    await update.message.reply_text("🔎 Searching for a partner...")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = chats.pop(user_id, None)
    if partner_id:
        chats.pop(partner_id, None)
        await context.bot.send_message(partner_id, "❗Your partner has left the chat.")
        await update.message.reply_text("You have left the chat.")
    elif user_id in waiting_users:
        waiting_users.remove(user_id)
        await update.message.reply_text("❌ You left the waiting queue.")
    else:
        await update.message.reply_text("You're not in a chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text
    for word in filtered_words:
        if word in msg.lower():
            return await update.message.reply_text("⚠️ Inappropriate content blocked.")
    if user_id in chats:
        partner_id = chats[user_id]
        typing_action(context, partner_id)
        await context.bot.send_message(partner_id, msg)
    else:
        await update.message.reply_text("❌ You're not in a chat.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available commands:\n/start\n/connect\n/disconnect\n/help")

# ===== MAIN =====
if __name__ == '__main__':
    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("connect", connect))
    app_bot.add_handler(CommandHandler("disconnect", disconnect))
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    from flask import Flask, request
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is live."

@app.route(f"/webhook/7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    application.update_queue.put(update)
    return "ok"

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url="https://your-app-name.onrender.com/webhook/7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk")
    print("Webhook set.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
        
