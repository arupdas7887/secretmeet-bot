import asyncio
import logging
import uuid
from datetime import datetime
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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
# !!! IMPORTANT: Replace this with your actual Telegram User ID to receive feedback !!!
ADMIN_USER_ID = 5246076255 # Example: Replace with your User ID. Find it using a bot like @userinfobot

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage for user data
user_data_store = {}

# Conversation states for feedback
FEEDBACK_MESSAGE = 1

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
    
    potential_matches.sort(key=lambda x: x["last_active"])

    if potential_matches:
        return potential_matches[0]
    return None

# Utility functions for keyboards
def get_inline_actions_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
        [InlineKeyboardButton("✉️ Send Feedback", callback_data="send_feedback")],
        [InlineKeyboardButton("🔄 Restart (Clear Match Status)", callback_data="restart_profile")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_command_reply_keyboard():
    keyboard = [
        [KeyboardButton("/start"), KeyboardButton("/help"), KeyboardButton("/end")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    await create_user(user_id, username, full_name)
    
    await update.message.reply_text(
        f"Welcome to The Secret Meet, {full_name}! What would you like to do?",
        reply_markup=get_command_reply_keyboard(), # Show persistent command keyboard
    )
    # Send the inline action buttons in a separate message
    await update.message.reply_text(
        "Choose an action:",
        reply_markup=get_inline_actions_keyboard()
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

    await query.edit_message_text("Your match status has been cleared.")
    # Send a new message with inline actions
    await context.bot.send_message(
        chat_id=user_id,
        text="What would you like to do next?",
        reply_markup=get_inline_actions_keyboard()
    )
    return ConversationHandler.END

async def send_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("Please type and send your feedback message. You can type /cancel to go back to the main menu at any time.")
    return FEEDBACK_MESSAGE # Enter feedback conversation state

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    if feedback_text == "/cancel":
        await update.message.reply_text(
            "Feedback cancelled.",
            reply_markup=get_inline_actions_keyboard()
        )
        return ConversationHandler.END

    # Forward the feedback to the admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"Feedback from User {user_id} (@{update.effective_user.username or 'N/A'}):\n\n{feedback_text}"
        )
        await update.message.reply_text("Thank you for your feedback! It has been sent.", reply_markup=get_inline_actions_keyboard())
        logger.info(f"Feedback received from {user_id} and forwarded to admin.")
    except Exception as e:
        logger.error(f"Failed to forward feedback from {user_id} to admin {ADMIN_USER_ID}: {e}")
        await update.message.reply_text("There was an error sending your feedback. Please try again later.", reply_markup=get_inline_actions_keyboard())

    return ConversationHandler.END # End the feedback conversation

async def end_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        
        for uid, udata in user_data_store.items():
            if udata.get('match_id') == match_id:
                udata['in_search'] = False
                udata['match_id'] = None
                udata['last_active'] = datetime.now()

        await update.message.reply_text("You have ended the chat. You are now out of the queue.")
        logger.info(f"Chat {match_id} ended by user {user_id}.")
    else:
        await update.message.reply_text("You are not currently in a chat or searching.")

    # Send a new message with inline actions after ending chat
    await update.message.reply_text(
        "What would you like to do next?",
        reply_markup=get_inline_actions_keyboard(),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here's how to use The Secret Meet:\n\n"
        "Use the small buttons at the bottom: /start, /help, /end.\n\n"
        "Press '🔍 Find a Match' to connect with someone new.\n"
        "Type /end to stop an ongoing chat.\n"
        "Use '✉️ Send Feedback' to share your thoughts directly.\n"
        "Press '🔄 Restart' to clear your current match status.\n\n"
        "Simply send a message when in a chat to talk to your partner!",
        reply_markup=get_inline_actions_keyboard() # Show inline actions as part of help
    )

async def send_match_found_message(user1_id, user2_id, application_bot):
    match_id = uuid.uuid4()
    
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
        await application_bot.send_message(chat_id=user1_id, text=match_info_msg) 
        await application_bot.send_message(chat_id=user2_id, text=match_info_msg)
        logger.info(f"Match {match_id} found between {user1_id} and {user2_id}.")
    except Exception as e:
        logger.error(f"Error sending match found message: {e}")
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

        if len(users_in_search) >= 2:
            user1 = users_in_search[0]
            user2 = users_in_search[1]
            
            await send_match_found_message(user1['user_id'], user2['user_id'], application.bot)

        else:
            logger.info("No suitable matches found in the current queue.")

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    # Check if the user is in a feedback conversation first
    current_state = context.bot_data.get(f'user_{user_id}_state') # Assuming you store state in bot_data
    if current_state == FEEDBACK_MESSAGE:
        await receive_feedback(update, context)
        return

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
                await end_match(update, context)
        else:
            await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")
            await remove_user_from_search(user_id)
    else:
        await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")

async def post_init_callback(application: Application) -> None:
    logger.info("Running post_init_callback (no database init).")
    application.bot_data['matching_scheduler_task'] = application.create_task(matching_scheduler(application))
    logger.info("post_init_callback finished.")

async def post_shutdown_callback(application: Application) -> None:
    logger.info("Bot application shutting down (no database close).")
    pass

def main() -> None:
    webhook_url = os.getenv("WEBHOOK_URL")

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init_callback).post_shutdown(post_shutdown_callback).build()

    # Main Conversation Handler for general flow
    main_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={}, # No specific states in this main handler as profile setup is removed
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    application.add_handler(main_conv_handler)

    # Feedback Conversation Handler
    feedback_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(send_feedback_start, pattern='^send_feedback$')],
        states={
            FEEDBACK_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback),
                CommandHandler("cancel", receive_feedback) # Allow /cancel to exit feedback
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # End the feedback conversation, but keep main flow running
        }
    )
    application.add_handler(feedback_conv_handler)


    application.add_handler(CommandHandler("end", end_match))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(find_match_callback, pattern='^find_match$'))
    application.add_handler(CallbackQueryHandler(restart_profile_callback, pattern='^restart_profile$'))
    # The 'send_feedback' callback is now handled by feedback_conv_handler entry_points

    # This message handler needs to be last or handle states,
    # otherwise it will catch messages meant for conversation states.
    # Updated logic in forward_message to check for feedback state.
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
