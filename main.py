import os
import random
import logging
from flask import Flask, request
from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# === CONFIGURATION ===
TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
WEBHOOK_URL = "https://secretmeet-bot.onrender.com"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# === APP INIT ===
app_flask = Flask(__name__)
application = Application.builder().token(TOKEN).build()
bot = Bot(token=TOKEN)

# === DATA STORAGE ===
users = {}
waiting_users = []
referrals = {}
chat_pairs = {}
locked_gender_search = {}

# === ICEBREAKER QUESTIONS ===
icebreakers = [
    "What’s your favorite way to spend a weekend?",
    "If you could visit any country, where would you go?",
    "What’s something you're currently learning?",
    "Describe your perfect day."
]

# === HELPER FUNCTIONS ===
def get_keyboard(buttons):
    return ReplyKeyboardMarkup([[KeyboardButton(text=b) for b in row] for row in buttons], resize_keyboard=True)

def typing_simulation(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    return context.bot.send_chat_action(chat_id=chat_id, action="typing")

def filter_bad_words(text):
    bad_words = ["badword1", "badword2"]
    for word in bad_words:
        text = text.replace(word, "***")
    return text

def get_personality_tag():
    return random.choice(["🎯 Deep Thinker", "😄 Light-hearted", "🤝 Friendly", "🎭 Mysterious"])

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = {}

    keyboard = [
        [InlineKeyboardButton("🇮🇳 India", callback_data="country_India"), InlineKeyboardButton("🇺🇸 USA", callback_data="country_USA")],
        [InlineKeyboardButton("🇸🇦 Saudi", callback_data="country_Saudi"), InlineKeyboardButton("🇹🇭 Thailand", callback_data="country_Thailand")],
        [InlineKeyboardButton("Next", callback_data="country_more")]
    ]
    await update.message.reply_text("🌍 Select your country:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("country_"):
        country = query.data.split("_")[1]
        users[user_id]["country"] = country
        age_keyboard = [[InlineKeyboardButton(str(i), callback_data=f"age_{i}") for i in range(a, a+5)] for a in range(14, 51, 5)]
        await query.message.reply_text("🎂 Select your age:", reply_markup=InlineKeyboardMarkup(age_keyboard))

    elif query.data.startswith("age_"):
        age = query.data.split("_")[1]
        users[user_id]["age"] = age
        gender_keyboard = [
            [InlineKeyboardButton("♂️ Male", callback_data="gender_Male"), InlineKeyboardButton("♀️ Female", callback_data="gender_Female")]
        ]
        await query.message.reply_text("🚻 Select your gender:", reply_markup=InlineKeyboardMarkup(gender_keyboard))

    elif query.data.startswith("gender_"):
        gender = query.data.split("_")[1]
        users[user_id]["gender"] = gender
        personality = get_personality_tag()
        users[user_id]["tag"] = personality

        buttons = [["🔍 Find a Partner"], ["🎯 Search by Gender"]]
        await query.message.reply_text(
            f"✅ Setup complete!\n🌍 Country: {users[user_id]['country']}\n🎂 Age: {users[user_id]['age']}\n🚻 Gender: {gender}\n🧠 Tag: {personality}",
            reply_markup=get_keyboard(buttons)
        )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    typing_simulation(context, user_id)

    if user_id in chat_pairs:
        await update.message.reply_text("⚠️ You are already in a chat. Use /disconnect first.")
        return

    if waiting_users:
        partner_id = waiting_users.pop(0)
        chat_pairs[user_id] = partner_id
        chat_pairs[partner_id] = user_id

        await context.bot.send_message(chat_id=user_id, text="✅ Partner found! Say hi!\n💡 Icebreaker: " + random.choice(icebreakers))
        await context.bot.send_message(chat_id=partner_id, text="✅ Partner found! Say hi!\n💡 Icebreaker: " + random.choice(icebreakers))
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⏳ Searching for a partner... Please wait.")

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in chat_pairs:
        partner_id = chat_pairs.pop(user_id)
        chat_pairs.pop(partner_id, None)

        await context.bot.send_message(chat_id=partner_id, text="❗Your partner has left the chat.")
        await update.message.reply_text("❗You left the chat.")

        # Feedback
        buttons = [[InlineKeyboardButton("👍", callback_data="feedback_good"), InlineKeyboardButton("👎", callback_data="feedback_bad")]]
        await context.bot.send_message(chat_id=user_id, text="How was your chat?", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text("⚠️ You are not in a chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = filter_bad_words(update.message.text)

    if user_id in chat_pairs:
        partner_id = chat_pairs[user_id]
        typing_simulation(context, partner_id)
        await context.bot.send_message(chat_id=partner_id, text=message)
    else:
        await update.message.reply_text("⚠️ You are not in a chat. Use /connect to find a partner.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""🤖 Available Commands:
/start – Begin and set your profile
/connect – Find a partner to chat
/disconnect – Leave the chat
/profile – View your info
/referral – Invite friends
/help – Show this message
""")

# === FLASK SETUP ===
@app_flask.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        application.update_queue.put_nowait(update)
        return "ok"
    return "Bot is running."

# === MAIN ===
if __name__ == "__main__":
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("disconnect", disconnect))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    bot.set_webhook(f"{WEBHOOK_URL}")
    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
