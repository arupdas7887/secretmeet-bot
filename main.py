import asyncio
import logging
import uuid
from datetime import datetime
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    Application
)

# Configuration
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage for user data
# Data structure: {user_id: {username: "...", full_name: "...", in_search: bool, match_id: UUID}}
user_data_store = {}

# User Data Operations (simulated with in-memory dict)
async def get_user(user_id: int):
    return user_data_store.get(user_id)

async def create_user(user_id: int, username: str, full_name: str):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "in_search": False,
            "match_id": None,
            "last_active": datetime.now(),
            "created_at": datetime.now()
        }
        logger.info(f"User {user_id} created in memory.")
    else:
        # Update existing user's username/full_name if they change
        user_data_store[user_id]["username"] = username
        user_data_store[user_id]["full_name"] = full_name
        logger.info(f"User {user_id} already exists in memory, updated info.")

async def update_user(user_id: int, **kwargs):
    if user_id in user_data_store:
        user_data_store[user_id].update(kwargs)
        user_data_store[user_id]["last_active"] = datetime.now() # Update last active on any interaction
        logger.info(f"User {user_id} updated in memory with {kwargs}.")
    else:
        logger.warning(f"Attempted to update non-existent user {user_id} in memory.")

async def remove_user_from_search(user_id: int):
    if user_id in user_data_store:
        user_data_store[user_id]["in_search"] = False
        user_data_store[user_id]["match_id"] = None
        user_data_store[user_id]["last_active"] = datetime.now()
        logger.info(f"User {user_id} removed from search queue in memory.")

async def set_user_in_search(user_id: int, in_search: bool = True):
    if user_id in user_data_store:
        user_data_store[user_id]["in_search"] = in_search
        user_data_store[user_id]["last_active"] = datetime.now()
        logger.info(f"User {user_id} in_search set to {in_search} in memory.")

async def find_matching_users(user_id: int):
    current_user = await get_user(user_id)
    if not current_user:
        return None

    potential_matches = [
        user for user_id, user in user_data_store.items()
        if user["in_search"] and user["user_id"] != current_user["user_id"]
    ]
    
    # Sort by last_active to try to match more active users, pick the oldest for fairness
    potential_matches.sort(key=lambda x: x["last_active"])

    if potential_matches:
        return potential_matches[0] # Return the first suitable match
    return None

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    await create_user(user_id, username, full_name)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
        [InlineKeyboardButton("🔄 Restart (Clear Match Status)", callback_data="restart_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Welcome to The Secret Meet, {full_name}! What would you like to do?",
        reply_markup=reply_markup,
    )
    return ConversationHandler.END

async def find_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    await set_user_in_search(user_id, True)
    await query.edit_message_text("Searching for a match now...")
    logger.info(f"User {user_id} clicked Find a Match and is now in search.")
    return ConversationHandler.END

async def restart_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    await update_user(user_id, in_search=False, match_id=None)
    logger.info(f"User {user_id} restarted/cleared match status.")

    keyboard = [
        [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
        [InlineKeyboardButton("🔄 Restart (Clear Match Status)", callback_data="restart_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Your match status has been cleared. What would you like to do next?",
        reply_markup=reply_markup,
    )
    return ConversationHandler.END

async def end_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        
        # Find both users in the match_id
        for uid, udata in user_data_store.items():
            if udata.get('match_id') == match_id:
                udata['in_search'] = False
                udata['match_id'] = None
                udata['last_active'] = datetime.now()

        await update.message.reply_text("You have ended the chat. You are now out of the queue.")
        logger.info(f"Chat {match_id} ended by user {user_id}.")
    else:
        await update.message.reply_text("You are not currently in a chat or searching.")

    keyboard = [
        [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
        [InlineKeyboardButton("🔄 Restart (Clear Match Status)", callback_data="restart_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "What would you like to do next?",
        reply_markup=reply_markup,
    )

async def send_match_found_message(user1_id, user2_id, application_bot): # Changed context.bot to application_bot for clarity
    match_id = uuid.uuid4()
    
    # Update users in in-memory store
    if user1_id in user_data_store:
        user_data_store[user1_id]['in_search'] = False
        user_data_store[user1_id]['match_id'] = match_id
    if user2_id in user_data_store:
        user_data_store[user2_id]['in_search'] = False
        user_data_store[user2_id]['match_id'] = match_id

    match_info_msg = (
        "🎉 Match found! 🎉\n\n"
        "You've been connected with a new partner. Say hello!\n\n"
        "To end the chat, type /end"
    )

    try:
        # Corrected: Use application_bot instead of context.bot directly
        await application_bot.send_message(chat_id=user1_id, text=match_info_msg) 
        await application_bot.send_message(chat_id=user2_id, text=match_info_msg)
        logger.info(f"Match {match_id} found between {user1_id} and {user2_id}.")
    except Exception as e:
        logger.error(f"Error sending match found message: {e}")
        # Revert search status if message fails
        if user1_id in user_data_store:
            user_data_store[user1_id]['in_search'] = True
            user_data_store[user1_id]['match_id'] = None
        if user2_id in user_data_store:
            user_data_store[user2_id]['in_search'] = True
            user_data_store[user2_id]['match_id'] = None

async def matching_scheduler(application: Application):
    while True:
        await asyncio.sleep(15)
        
        users_in_search = [
            user for user_id, user in user_data_store.items()
            if user["in_search"] and user["match_id"] is None
        ]
        
        logger.info(f"Attempting to find and match users... {len(users_in_search)} users in queue (in-memory).")

        if len(users_in_search) < 2:
            logger.info("Not enough users in queue for matching.")
            continue

        # Simple FIFO matching for now
        if len(users_in_search) >= 2:
            user1 = users_in_search[0]
            user2 = users_in_search[1]
            
            # Pass application.bot directly to the function
            await send_match_found_message(user1['user_id'], user2['user_id'], application.bot)

        else:
            logger.info("No suitable matches found in the current queue.")


async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        
        partner_id = None
        for uid, udata in user_data_store.items():
            if udata.get('match_id') == match_id and uid != user_id:
                partner_id = uid
                break
        
        if partner_id:
            try:
                await context.bot.forward_message(
                    chat_id=partner_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                logger.info(f"Message from {user_id} forwarded to {partner_id}.")
            except Exception as e:
                logger.error(f"Error forwarding message from {user_id} to {partner_id}: {e}")
                await update.message.reply_text("Could not send your message to your partner. They might have left or blocked the bot.")
                await end_match(update, context) # Automatically end match if forwarding fails
        else:
            await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")
            await remove_user_from_search(user_id) # Ensure user is out of search
    else:
        await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")

async def post_init_callback(application: Application) -> None:
    logger.info("Running post_init_callback (no database init).")
    application.bot_data['matching_scheduler_task'] = application.create_task(matching_scheduler(application))
    logger.info("post_init_callback finished.")

async def post_shutdown_callback(application: Application) -> None:
    logger.info("Bot application shutting down (no database close).")
    pass # No action needed for in-memory store shutdown

def main() -> None:
    webhook_url = os.getenv("WEBHOOK_URL")

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init_callback).post_shutdown(post_shutdown_callback).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("end", end_match))
    application.add_handler(CallbackQueryHandler(find_match_callback, pattern='^find_match$'))
    application.add_handler(CallbackQueryHandler(restart_profile_callback, pattern='^restart_profile$'))

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))

    if webhook_url:
        logger.info(f"Running with Webhook: {webhook_url}/{BOT_TOKEN}")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            url_path=BOT_TOKEN,
            webhook_url=f"{webhook_url}/{BOT_TOKEN}"
        )
    else:
        logger.info("Running with Polling (WEBHOOK_URL not set).")
        application.run_polling(poll_interval=3)

if __name__ == "__main__":
    main()
