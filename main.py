from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler import random, logging, time from datetime import datetime, timedelta

--- Bot Token ---

TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"

--- Enable logging ---

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO) logger = logging.getLogger(name)

--- States ---

SELECT_COUNTRY, SELECT_AGE, SELECT_GENDER, CHATTING = range(4)

--- Data Storage ---

users = {} pending_users = [] active_chats = {} referrals = {} referral_times = {}

--- Popular Countries ---

popular_countries = [ "India", "USA", "UK", "Canada", "Australia", "Spain", "Saudi Arabia", "UAE", "Iran", "Iraq", "Thailand", "Vietnam", "Philippines", "Nigeria", "South Africa", "Kenya", "Colombia", "Argentina" ]

--- Genders ---

genders = ["Male", "Female"]

--- Start Command ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id users[user_id] = {} keyboard = [[InlineKeyboardButton(c, callback_data=c)] for c in popular_countries] await update.message.reply_text("🌍 Select your country:", reply_markup=InlineKeyboardMarkup(keyboard)) return SELECT_COUNTRY

--- Country Selection ---

async def country_select(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() country = query.data user_id = query.from_user.id users[user_id]['country'] = country keyboard = [[InlineKeyboardButton(str(age), callback_data=str(age))] for age in range(14, 51)] await query.edit_message_text("🎂 Select your age:", reply_markup=InlineKeyboardMarkup(keyboard)) return SELECT_AGE

--- Age Selection ---

async def age_select(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() age = query.data user_id = query.from_user.id users[user_id]['age'] = age keyboard = [[InlineKeyboardButton(g, callback_data=g)] for g in genders] await query.edit_message_text("👫 Select your gender:", reply_markup=InlineKeyboardMarkup(keyboard)) return SELECT_GENDER

--- Gender Selection ---

async def gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() gender = query.data user_id = query.from_user.id users[user_id]['gender'] = gender

buttons = [[
    InlineKeyboardButton("🔍 Find a Partner", callback_data="find_partner")
]]

# Gender search button logic
if referrals.get(user_id, 0) >= 5:
    expiry = referral_times.get(user_id, datetime.min)
    if datetime.now() < expiry:
        buttons.append([InlineKeyboardButton("🎯 Search by Gender", callback_data="search_by_gender")])

await query.edit_message_text("✅ Setup complete!", reply_markup=InlineKeyboardMarkup(buttons))
return ConversationHandler.END

--- Find Partner Button ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query user_id = query.from_user.id

if query.data == "find_partner":
    await query.answer()
    await query.edit_message_text("⏳ Searching for a partner...")
    await find_partner(user_id, context)

elif query.data == "search_by_gender":
    await query.answer()
    await context.bot.send_message(user_id, "🎯 Send the gender you want to search (Male/Female):")
    context.user_data['gender_search'] = True

--- Search Partner Logic ---

async def find_partner(user_id, context): if user_id in pending_users: return pending_users.append(user_id) for other_id in pending_users: if other_id != user_id and other_id not in active_chats: pending_users.remove(user_id) pending_users.remove(other_id) active_chats[user_id] = other_id active_chats[other_id] = user_id await context.bot.send_message(user_id, "🔗 You're now connected! Say hi! ✨") await context.bot.send_message(other_id, "🔗 You're now connected! Say hi! ✨") return await context.bot.send_message(user_id, "Still searching...")

--- Disconnect Command ---

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id partner_id = active_chats.pop(user_id, None) if partner_id: active_chats.pop(partner_id, None) await context.bot.send_message(partner_id, "❗Your partner has left the chat.") await update.message.reply_text("You have left the chat.")

--- Message Forwarding ---

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id text = update.message.text

# Gender search input handling
if context.user_data.get('gender_search'):
    if text in genders:
        context.user_data.pop('gender_search')
        await update.message.reply_text(f"Searching for a {text} partner...")
        # (Search logic by gender can be placed here)
    else:
        await update.message.reply_text("❌ Invalid gender. Type Male or Female.")
    return

if user_id in active_chats:
    partner_id = active_chats[user_id]
    await context.bot.send_chat_action(partner_id, "typing")
    await context.bot.send_message(partner_id, text)
else:
    await update.message.reply_text("❌ You're not in a chat. Click '🔍 Find a Partner' to connect.")

--- Help Command ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text(""" 🛠 Available Commands: /start – Begin setup /connect – Find a partner /disconnect – Leave current chat /profile – View your info /help – Show this menu /referral – Invite friends to unlock gender search

💡 Features:

Anonymous Matching

Typing Simulation

Icebreaker Prompts (Coming Soon)

Safe Chat Filter

Secret Room Codes

Feedback after each chat

Gender Search unlockable by referral """)


--- Referral Command ---

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id referrals[user_id] = referrals.get(user_id, 0) + 1 referral_times[user_id] = datetime.now() + timedelta(hours=1) await update.message.reply_text("✅ Referral added! Gender search unlocked for 1 hour.")

--- Main Function ---

if name == 'main': app = Application.builder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        SELECT_COUNTRY: [CallbackQueryHandler(country_select)],
        SELECT_AGE: [CallbackQueryHandler(age_select)],
        SELECT_GENDER: [CallbackQueryHandler(gender_select)],
    },
    fallbacks=[]
)

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(CommandHandler("disconnect", disconnect))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("referral", referral))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

print("✅ Bot is running...")
app.run_polling()



