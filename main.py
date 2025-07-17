import logging import random import string import asyncio from datetime import datetime, timedelta from collections import defaultdict from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton) from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler)

--- CONFIGURATION ---

TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk" POPULAR_COUNTRIES = ["Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand", "Vietnam", "Philippines", "Nigeria", "South Africa", "Kenya", "Colombia", "Argentina"]

--- GLOBAL STATE ---

user_data = {} waiting_users = [] active_chats = {} referrals = defaultdict(lambda: {"count": 0, "unlocked_at": None}) secret_rooms = defaultdict(list)

--- LOGGING ---

logging.basicConfig(level=logging.INFO) logger = logging.getLogger(name)

--- UTILITIES ---

def generate_room_code(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def referral_unlocked(user_id): data = referrals[user_id] if data["unlocked_at"]: return datetime.now() < data["unlocked_at"] + timedelta(hours=1) return False

async def send_typing(context, chat_id): await context.bot.send_chat_action(chat_id=chat_id, action="typing") await asyncio.sleep(1.5)

--- START COMMAND ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): keyboard = [[InlineKeyboardButton(country, callback_data=f"country_{country}")] for country in POPULAR_COUNTRIES] await update.message.reply_text("🌍 Select your country:", reply_markup=InlineKeyboardMarkup(keyboard)) return 1

async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() country = query.data.split("")[1] user_data[query.from_user.id] = {"country": country} keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age{age}")] for age in range(14, 51)] await query.edit_message_text("🎂 Select your age:", reply_markup=InlineKeyboardMarkup(keyboard)) return 2

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() age = int(query.data.split("_")[1]) user_data[query.from_user.id]["age"] = age keyboard = [[InlineKeyboardButton("Male", callback_data="gender_Male"), InlineKeyboardButton("Female", callback_data="gender_Female")]] await query.edit_message_text("👫 Select your gender:", reply_markup=InlineKeyboardMarkup(keyboard)) return 3

async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() gender = query.data.split("_")[1] user_data[query.from_user.id]["gender"] = gender

find_partner = KeyboardButton("🔍 Find a Partner")
if referral_unlocked(query.from_user.id):
    search_by_gender = KeyboardButton("🎯 Search by Gender")
    keyboard = [[find_partner, search_by_gender]]
else:
    keyboard = [[find_partner]]

await query.edit_message_text("✅ Setup complete! Use the buttons below to start chatting.")
await context.bot.send_message(chat_id=query.from_user.id,
                               text="Select an option:",
                               reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
return ConversationHandler.END

--- CONNECT & CHAT ---

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.message.from_user.id if user_id in active_chats: await update.message.reply_text("❗You are already in a chat. Use /disconnect first.") return

if waiting_users:
    partner_id = waiting_users.pop(0)
    active_chats[user_id] = partner_id
    active_chats[partner_id] = user_id
    await context.bot.send_message(partner_id, "✅ You are now connected to a partner!")
    await context.bot.send_message(user_id, "✅ You are now connected to a partner!")
else:
    waiting_users.append(user_id)
    await update.message.reply_text("⏳ Waiting for a partner to connect...")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.message.from_user.id if user_id in active_chats: partner_id = active_chats.pop(user_id) active_chats.pop(partner_id, None) await context.bot.send_message(partner_id, "❗Your partner has left the chat.") await update.message.reply_text("❌ You have disconnected.") elif user_id in waiting_users: waiting_users.remove(user_id) await update.message.reply_text("❌ You have left the queue.") else: await update.message.reply_text("❗You are not in a chat or queue.")

--- RUN APPLICATION ---

if name == "main": app = Application.builder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        1: [CallbackQueryHandler(select_country)],
        2: [CallbackQueryHandler(select_age)],
        3: [CallbackQueryHandler(select_gender)],
    },
    fallbacks=[]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("connect", connect))
app.add_handler(CommandHandler("disconnect", disconnect))

app.run_polling()

