from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import os
import random

TOKEN = "7673817380:

AAH8NkM1A3kJzB9HVdWB1rkTIaMBeol6Nyk"

users = {}
waiting_users = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇳 India", callback_data="country_India")],
        [InlineKeyboardButton("🇺🇸 USA", callback_data="country_USA")],
        [InlineKeyboardButton("🇬🇧 UK", callback_data="country_UK")],
        [InlineKeyboardButton("➡️ More Countries", callback_data="country_more")]
    ]
    await update.message.reply_text("🌍 Select your country:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data.startswith("country_"):
        users[user_id] = {"country": query.data.replace("country_", "")}
        keyboard = [
            [InlineKeyboardButton("14-18", callback_data="age_14-18")],
            [InlineKeyboardButton("19-25", callback_data="age_19-25")],
            [InlineKeyboardButton("26-35", callback_data="age_26-35")],
            [InlineKeyboardButton("36+", callback_data="age_36+")]
        ]
        await query.edit_message_text("🎂 Select your age range:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("age_"):
        users[user_id]["age"] = query.data.replace("age_", "")
        keyboard = [[InlineKeyboardButton("🔍 Find a Partner", callback_data="find_partner")]]
        await query.edit_message_text("✅ You're set up! Now find a chat partner:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "find_partner":
        if user_id in waiting_users:
            await query.edit_message_text("⏳ Still waiting for a partner...")
            return
        if waiting_users:
            partner_id = waiting_users.pop(0)
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            await context.bot.send_message(chat_id=user_id, text="✅ You are now connected! Say hi 👋")
            await context.bot.send_message(chat_id=partner_id, text="✅ You are now connected! Say hi 👋")
        else:
            waiting_users.append(user_id)
            await query.edit_message_text("⏳ Waiting for a partner...")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.from_user.id
    if sender_id in users and "partner" in users[sender_id]:
        partner_id = users[sender_id]["partner"]
        if partner_id in users:
            await context.bot.send_chat_action(chat_id=partner_id, action="typing")
            await context.bot.send_message(chat_id=partner_id, text=update.message.text)
    else:
        await update.message.reply_text("❗You are not in a chat. Tap /start to begin.")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in users and "partner" in users[user_id]:
        partner_id = users[user_id]["partner"]
        await context.bot.send_message(chat_id=partner_id, text="❗Your partner has left the chat.")
        users[partner_id].pop("partner", None)
        users[user_id].pop("partner", None)
        await update.message.reply_text("❌ Disconnected.")
    else:
        await update.message.reply_text("❗You're not connected to anyone.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("disconnect", disconnect))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

app.run_polling()
