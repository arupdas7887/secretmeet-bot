import logging
import time
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "7673817380:AAH8NKM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
BOT_USERNAME = "TheSecretMeet_bot"

GENDER_OPTIONS = ["♂️ Male", "♀️ Female", "⚧️ Other"]
REFERRAL_TARGET = 3
UNLOCK_DURATION = 3600  # 1 hour in seconds

# --- MEMORY STORAGE (for demonstration) ---
waiting_users = []
active_chats = {}
user_genders = {}
user_referrals = {}
user_ref_counts = {}
gender_unlocked_until = {}

# --- KEYBOARDS ---
main_keyboard = ReplyKeyboardMarkup(
    [["🔗 Connect", "🎯 Match by Gender", "📣 Get My Referral Link"]],
    resize_keyboard=True
)
chat_keyboard = ReplyKeyboardMarkup(
    [["➡️ Skip", "✋ End Chat"]],
    resize_keyboard=True
)

def get_share_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start=ref{user_id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    # Referral logic
    if args and args[0].startswith('ref'):
        referrer_id = int(args[0][3:])
        if referrer_id != user_id and user_id not in user_referrals:
            user_referrals[user_id] = referrer_id
            user_ref_counts[referrer_id] = user_ref_counts.get(referrer_id, 0) + 1
            if user_ref_counts[referrer_id] == REFERRAL_TARGET:
                gender_unlocked_until[referrer_id] = int(time.time()) + UNLOCK_DURATION
                await context.bot.send_message(
                    referrer_id,
                    "🎉 You've unlocked 'Match by Gender' for 1 hour! Go try it now.",
                    reply_markup=main_keyboard
                )
    await update.message.reply_text(
        "👋 Welcome to The Secret Meet!\n\nChoose what you want to do:",
        reply_markup=main_keyboard
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "🔗 Connect":
        await start_chat(update, context, user_id)
    elif text == "🎯 Match by Gender":
        if can_use_gender_search(user_id):
            await ask_gender_choice(update, context)
        else:
            await send_premium_options(update, context, user_id)
    elif text == "📣 Get My Referral Link":
        await send_share_link(update, context)
    elif text == "➡️ Skip":
        await skip_partner(update, context, user_id)
    elif text == "✋ End Chat":
        await end_chat(update, context, user_id)
    elif text in GENDER_OPTIONS:
        user_genders[user_id] = text
        await find_gender_match(update, context, user_id, text)
    else:
        # Relay chat message if in chat
        partner_id = active_chats.get(user_id)
        if partner_id:
            await context.bot.send_message(partner_id, text)

def can_use_gender_search(user_id):
    return gender_unlocked_until.get(user_id, 0) > int(time.time())

async def ask_gender_choice(update, context):
    await update.message.reply_text(
        "Select the gender you want to chat with:",
        reply_markup=ReplyKeyboardMarkup(
            [[g] for g in GENDER_OPTIONS], resize_keyboard=True
        )
    )

async def send_premium_options(update, context, user_id):
    share_link = get_share_link(user_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Share & Unlock", url=f"https://t.me/share/url?url={share_link}&text=Join%20this%20cool%20anonymous%20chat!")],
        [InlineKeyboardButton("💳 Go Premium", url="https://your-payment-link.com")]
    ])
    referred = user_ref_counts.get(user_id, 0)
    await update.message.reply_text(
        f"🔒 'Match by Gender' is a premium feature.\n"
        f"Invite {REFERRAL_TARGET} friends to unlock 1 hour free (You have {referred}/{REFERRAL_TARGET}), or go premium.",
        reply_markup=keyboard
    )

async def send_share_link(update, context):
    user_id = update.effective_user.id
    share_link = get_share_link(user_id)
    await update.message.reply_text(
        f"📣 Share this link with your friends. When 3 friends join, you'll unlock 'Match by Gender' for 1 hour!\n\n{share_link}"
    )

async def start_chat(update, context, user_id):
    if user_id in active_chats:
        await end_chat(update, context, user_id)
    for other in waiting_users:
        if other != user_id and other not in active_chats:
            active_chats[user_id] = other
            active_chats[other] = user_id
            waiting_users.remove(other)
            await context.bot.send_message(other, "🔗 You're connected! Say hi!", reply_markup=chat_keyboard)
            await update.message.reply_text("🔗 You're connected! Say hi!", reply_markup=chat_keyboard)
            return
    if user_id not in waiting_users:
        waiting_users.append(user_id)
    await update.message.reply_text("⏳ Waiting for a partner...", reply_markup=main_keyboard)

async def skip_partner(update, context, user_id):
    await end_chat(update, context, user_id)
    await start_chat(update, context, user_id)

async def end_chat(update, context, user_id):
    partner_id = active_chats.pop(user_id, None)
    if partner_id:
        active_chats.pop(partner_id, None)
        await context.bot.send_message(partner_id, "❗️ Your partner has left the chat.", reply_markup=main_keyboard)
    await update.message.reply_text("You left the chat.", reply_markup=main_keyboard)

async def find_gender_match(update, context, user_id, gender_choice):
    if user_id in active_chats:
        await end_chat(update, context, user_id)
    for other, g in user_genders.items():
        if other != user_id and g == gender_choice and other not in active_chats:
            active_chats[user_id] = other
            active_chats[other] = user_id
            await context.bot.send_message(other, "🎯 Gender match found! Say hi!", reply_markup=chat_keyboard)
            await update.message.reply_text("🎯 Gender match found! Say hi!", reply_markup=chat_keyboard)
            return
    await update.message.reply_text("⏳ Waiting for a partner…", reply_markup=main_keyboard)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass  # For future inline button callbacks

def main():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.run_polling()

if __name__ == "__main__":
    main()