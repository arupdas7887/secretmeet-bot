import logging import random import string import time from datetime import datetime, timedelta from collections import defaultdict from flask import Flask from threading import Thread

from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove) from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler)

TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"

logging.basicConfig(level=logging.INFO)

app = Flask('')

def keep_alive(): @app.route('/') def home(): return "Bot is running" Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

==== Data Stores ====

users = {} chats = {} queue = [] referrals = defaultdict(list) feature_unlocks = {} secret_rooms = {} personalities = {}

==== Constants ====

COUNTRIES = ["India", "USA", "UK", "Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand", "Vietnam", "Philippines", "Nigeria", "South Africa", "Kenya", "Colombia", "Argentina"] AGES = list(map(str, range(14, 51))) ICEBREAKERS = ["What's your favorite movie?", "What's your dream vacation?", "One thing you can't live without?", "If you could time travel, past or future?"] FILTER_WORDS = ["badword1", "badword2"]

==== Utils ====

def paginate_keyboard(options, prefix, page=0, per_page=6): buttons = [InlineKeyboardButton(opt, callback_data=f"{prefix}:{opt}") for opt in options[page*per_page:(page+1)*per_page]] keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)] nav_buttons = [] if page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}_page:{page-1}")) if (page+1)*per_page < len(options): nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"{prefix}_page:{page+1}")) if nav_buttons: keyboard.append(nav_buttons) return InlineKeyboardMarkup(keyboard)

def clean_text(text): for word in FILTER_WORDS: text = text.replace(word, "***") return text

def is_feature_unlocked(user_id): if user_id in feature_unlocks and datetime.now() < feature_unlocks[user_id]: return True return False

def unlock_feature(user_id): feature_unlocks[user_id] = datetime.now() + timedelta(hours=1)

==== Handlers ====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user users[user.id] = {'step': 'country'} await update.message.reply_text("🌍 Select your country:", reply_markup=paginate_keyboard(COUNTRIES, "country"))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() user_id = query.from_user.id

data = query.data

if data.startswith("country_page"):
    page = int(data.split(":")[1])
    await query.edit_message_reply_markup(paginate_keyboard(COUNTRIES, "country", page))

elif data.startswith("country:"):
    country = data.split(":")[1]
    users[user_id]['country'] = country
    users[user_id]['step'] = 'age'
    await query.edit_message_text("🎂 Select your age:", reply_markup=paginate_keyboard(AGES, "age"))

elif data.startswith("age_page"):
    page = int(data.split(":")[1])
    await query.edit_message_reply_markup(paginate_keyboard(AGES, "age", page))

elif data.startswith("age:"):
    age = data.split(":")[1]
    users[user_id]['age'] = age
    users[user_id]['step'] = 'gender'
    gender_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("♂️ Male", callback_data="gender:Male"), InlineKeyboardButton("♀️ Female", callback_data="gender:Female")]
    ])
    await query.edit_message_text("👤 Select your gender:", reply_markup=gender_kb)

elif data.startswith("gender:"):
    gender = data.split(":")[1]
    users[user_id]['gender'] = gender
    users[user_id]['step'] = 'done'
    kb = ReplyKeyboardMarkup([["🔍 Find a Partner"], ["🎯 Search by Gender"]], resize_keyboard=True)
    await query.edit_message_text("✅ Setup complete!", reply_markup=None)
    await context.bot.send_message(chat_id=user_id, text="Use the buttons below to start chatting!", reply_markup=kb)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id msg = clean_text(update.message.text)

if msg == "🔍 Find a Partner":
    if user_id in chats:
        await update.message.reply_text("You're already in a chat. Type /disconnect to leave.")
        return
    queue.append(user_id)
    await update.message.reply_text("🔎 Searching for a partner...")
    if len(queue) >= 2:
        uid1 = queue.pop(0)
        uid2 = queue.pop(0)
        chats[uid1] = uid2
        chats[uid2] = uid1
        await context.bot.send_message(uid1, text="👤 Partner found! Say hi! \n💬 Icebreaker: " + random.choice(ICEBREAKERS))
        await context.bot.send_message(uid2, text="👤 Partner found! Say hi! \n💬 Icebreaker: " + random.choice(ICEBREAKERS))
elif msg == "🎯 Search by Gender":
    if not is_feature_unlocked(user_id):
        await update.message.reply_text("🔒 This feature is locked. Invite 5 friends using /referral to unlock for 1 hour.")
    else:
        await update.message.reply_text("Feature unlocked — Searching by gender coming soon ✨")
elif user_id in chats:
    partner_id = chats[user_id]
    await context.bot.send_chat_action(partner_id, action="typing")
    await context.bot.send_message(partner_id, text=msg)
else:
    await update.message.reply_text("Type /start to begin or /connect to find someone.")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id if user_id in chats: partner_id = chats.pop(user_id) chats.pop(partner_id, None) await context.bot.send_message(partner_id, text="❗Your partner has left the chat.") await update.message.reply_text("You left the chat. Type 🔍 Find a Partner to start again.") else: await update.message.reply_text("You're not in a chat.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("📜 Commands:\n/start - Begin setup\n/connect - Find random partner\n/disconnect - Leave current chat\n/referral - Get referral link\n/profile - View your info\n/help - Show this help menu")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE): user = users.get(update.effective_user.id, {}) text = f"🌍 Country: {user.get('country', 'N/A')}\n🎂 Age: {user.get('age', 'N/A')}\n👤 Gender: {user.get('gender', 'N/A')}" await update.message.reply_text(text)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id link = f"https://t.me/{context.bot.username}?start={uid}" await update.message.reply_text(f"📢 Share this link with 5 friends to unlock 🎯 Search by Gender for 1 hour:\n{link}")

==== Main ====

if name == 'main': keep_alive() app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
app.add_handler(CommandHandler("disconnect", disconnect))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("referral", referral))

app.run_polling()

