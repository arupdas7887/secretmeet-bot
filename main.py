from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler
)
from itertools import islice
import logging

# ===== CONFIGURATION =====
TOKEN = "7673817380 : AAH8NKM1A3kJzB9HVdWB1rkTIaMBeol6Nyk"
ADMIN_ID = "t.me/TheSecretMeet_bot"

# Complete country list with flags (200+ countries)
COUNTRIES = [
    "🇺🇸 United States", "🇬🇧 United Kingdom", "🇮🇳 India",
    "🇨🇦 Canada", "🇦🇺 Australia", "🇩🇪 Germany",
    # ... (full list from previous implementation)
    "Other"
]

# ===== SETUP =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== STORAGE =====
user_data = {}  # Stores user profiles
active_chats = {}  # Tracks active conversations
referral_data = {}  # Manages referral counts

# ===== STATES =====
GET_COUNTRY, GET_AGE = range(2)  # Conversation states

# ===== KEYBOARDS =====
def main_menu_keyboard():
    """Main menu with (/) button"""
    return ReplyKeyboardMarkup(
        [["🔍 /", "🔄 Next", "⛔ Stop"]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ===== CORE FUNCTIONS =====
def start(update: Update, context: CallbackContext) -> int:
    """Initialize onboarding with country selection"""
    context.user_data.clear()
    context.user_data['country_page'] = 0
    show_country_page(update, context)
    return GET_COUNTRY

def show_country_page(update: Update, context: CallbackContext, page: int = 0):
    """Display paginated country list"""
    items_per_page = 30
    start_idx = page * items_per_page
    page_countries = list(islice(COUNTRIES, start_idx, start_idx + items_per_page))
    
    keyboard = []
    for i in range(0, len(page_countries), 3):
        row = [
            InlineKeyboardButton(c, callback_data=f"country_{c}")
            for c in page_countries[i:i+3] if c
        ]
        if row:
            keyboard.append(row)
    
    if (start_idx + items_per_page) < len(COUNTRIES):
        keyboard.append([InlineKeyboardButton("More...", callback_data="country_more")])
    
    if update.callback_query:
        update.callback_query.edit_message_text(
            "🌍 Select your country:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text(
            "🌍 Select your country:",
            reply_markup=InlineKeyboardMarkup(keyboard))

def handle_country(update: Update, context: CallbackContext):
    """Process country selection"""
    query = update.callback_query
    query.answer()
    
    if query.data == "country_more":
        context.user_data['country_page'] += 1
        show_country_page(update, context, context.user_data['country_page'])
        return GET_COUNTRY
    else:
        country = query.data.split('_', 1)[1]
        context.user_data['country'] = country
        query.edit_message_text(f"Selected: {country}\n\n📆 Enter your age (13+):")
        return GET_AGE

def handle_age(update: Update, context: CallbackContext) -> int:
    """Process age input"""
    try:
        age = int(update.message.text)
        if age < 13:
            update.message.reply_text("❌ Minimum age is 13. Try again:")
            return GET_AGE
        
        user_id = update.effective_user.id
        user_data[user_id] = {
            'country': context.user_data['country'],
            'age': age,
            'nickname': f"Ghost_{user_id[-4:]}",
            'referrals': 0,
            'gender_filter': False
        }
        
        update.message.reply_text(
            f"✅ Registration complete!\n"
            f"Country: {user_data[user_id]['country']}\n"
            f"Age: {age}\n"
            f"Nickname: {user_data[user_id]['nickname']}\n\n"
            f"Use /profile to edit settings",
            reply_markup=main_menu_keyboard())
        
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("❌ Please enter numbers only (e.g. 25):")
        return GET_AGE

def profile(update: Update, context: CallbackContext):
    """Profile management"""
    user_id = update.effective_user.id
    if user_id not in user_data:
        update.message.reply_text("Please /start first")
        return
    
    keyboard = [
        [InlineKeyboardButton("🌍 Edit Country", callback_data="edit_country")],
        [InlineKeyboardButton("🎂 Edit Age", callback_data="edit_age")],
        [InlineKeyboardButton("✏️ Edit Nickname", callback_data="edit_nickname")],
        [InlineKeyboardButton("🗑️ Delete Data", callback_data="delete_data")]
    ]
    update.message.reply_text(
        f"👤 Your Profile:\n"
        f"━━━━━━━━━━━━\n"
        f"🌍 Country: {user_data[user_id]['country']}\n"
        f"🎂 Age: {user_data[user_id]['age']}\n"
        f"✏️ Nickname: {user_data[user_id]['nickname']}\n"
        f"🔑 Referrals: {user_data[user_id]['referrals']}/3\n"
        f"━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(keyboard))

# ===== MAIN =====
def main():
    print("🚀 Initializing Secret Meet Bot...")
    
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GET_COUNTRY: [CallbackQueryHandler(handle_country)],
            GET_AGE: [MessageHandler(Filters.text & ~Filters.command, handle_age)]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Command handlers
    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler('profile', profile))
    dp.add_handler(CommandHandler('test', lambda u,c: u.message.reply_text("✅ Bot is live!")))

    # Start polling
    updater.start_polling(
        drop_pending_updates=True,
        timeout=30,
        read_latency=2.0,
        poll_interval=0.1
    )
    print("✅ Bot is now LIVE with infinite polling")
    updater.idle()

if __name__ == '__main__':
    main()