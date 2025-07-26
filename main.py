import asyncio
import logging
import uuid
from datetime import datetime
import os

# --- MODIFIED: Import ChatAction from telegram.constants ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction 
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
ADMIN_USER_ID = 5246076255 # IMPORTANT: Replace with your actual Telegram User ID to receive feedback/reports!

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage for user data
user_data_store = {}

# Conversation states for general feedback
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
        user_data_store[user_id]["username"] = username
        user_data_store[user_id]["full_name"] = full_name
        logger.info(f"User {user_id} already exists in memory, updated info.")

async def update_user(user_id: int, **kwargs):
    if user_id in user_data_store:
        user_data_store[user_id].update(kwargs)
        user_data_store[user_id]["last_active"] = datetime.now()
        logger.info(f"User {user_id} updated in memory with {kwargs}.")
    else:
        logger.warning(f"Attempted to update non-existent user {user_id} in memory.")

async def remove_user_from_search(user_id: int):
    if user_id in user_data_store:
        user_data_store[user_id]["in_search"] = False
        user_data_store[user_id]["match_id"] = None
        user_data_store[user_id]["last_active"] = datetime.now()
        logger.info(f"User {user_id} removed from search queue in memory.")

# Utility functions for keyboards
def get_command_reply_keyboard():
    """Returns the persistent reply keyboard with Find Match and Stop Chat buttons."""
    keyboard = [
        [KeyboardButton("🔍 Find a Match")],
        [KeyboardButton("🛑 Stop Chat")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_post_chat_feedback_keyboard():
    """Returns the inline keyboard for post-chat feedback and reports."""
    keyboard = [
        [InlineKeyboardButton("👍", callback_data="chat_feedback_up"),
         InlineKeyboardButton("👎", callback_data="chat_feedback_down")],
        [InlineKeyboardButton("⚠️ Report —", callback_data="chat_feedback_report_start")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_report_reasons_keyboard():
    """Returns the inline keyboard with predefined report reasons."""
    keyboard = [
        [InlineKeyboardButton("Spam / Advertising", callback_data="report_reason_spam")],
        [InlineKeyboardButton("Harassment / Abuse", callback_data="report_reason_harassment")],
        [InlineKeyboardButton("Inappropriate Content", callback_data="report_reason_inappropriate")],
        [InlineKeyboardButton("← Back", callback_data="report_reason_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /start command, creates/updates user, and shows main keyboard."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    await create_user(user_id, username, full_name)
    
    await update.message.reply_text(
        f"Welcome to The Secret Meet, {full_name}! Use the buttons below to find a match or type /help.",
        reply_markup=get_command_reply_keyboard(), # Show persistent command keyboard
    )
    return ConversationHandler.END

async def find_next_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates the search for a new partner."""
    user_id = update.effective_user.id
    await update_user(user_id, in_search=True) # Use update_user for consistency
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Searching for a partner now...")
    else:
        await update.message.reply_text("Searching for a partner now...")
    logger.info(f"User {user_id} initiated search.")

# General Feedback Handlers (only accessible via /sendfeedback command)
async def send_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the feedback conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    else:
        await update.message.reply_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    return FEEDBACK_MESSAGE

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives and forwards general feedback to the admin."""
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    if feedback_text == "/cancel":
        await update.message.reply_text(
            "Feedback cancelled.",
            reply_markup=get_command_reply_keyboard() # Return to main reply keyboard
        )
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"Anonymous General Feedback:\n\n{feedback_text}"
        )
        await update.message.reply_text("Thank you for your feedback! It has been sent anonymously.", reply_markup=get_command_reply_keyboard())
        logger.info(f"Anonymous feedback received from {user_id} and forwarded to admin.")
    except Exception as e:
        logger.error(f"Failed to forward anonymous feedback from {user_id} to admin {ADMIN_USER_ID}: {e}")
        await update.message.reply_text("There was an error sending your feedback. Please try again later.", reply_markup=get_command_reply_keyboard())

    return ConversationHandler.END

# Post-Chat Feedback Handlers
async def handle_chat_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles positive/negative chat feedback."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    feedback_type = query.data.split('_')[-1]

    if feedback_type == 'up':
        await query.edit_message_text("👍 Thanks for your positive feedback!")
    elif feedback_type == 'down':
        await query.edit_message_text("👎 Sorry to hear that. We'll try to improve your matches.")
    
    # After feedback, ensure persistent reply keyboard is shown
    await context.bot.send_message(
        chat_id=user_id,
        text="You can find a new partner using the buttons below.",
        reply_markup=get_command_reply_keyboard()
    )

async def chat_feedback_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the chat reporting process by showing reasons."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Choose a reason for your report:",
        reply_markup=get_report_reasons_keyboard()
    )

async def handle_specific_report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of a specific report reason and sends it anonymously."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    reason = query.data.replace('report_reason_', '').replace('_', ' ').title()

    if reason == "Cancel":
        await query.edit_message_text(
            "Report cancelled. You can find a new partner using the buttons below.",
            reply_markup=get_command_reply_keyboard() # Return to main reply keyboard
        )
        return ConversationHandler.END
    else:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"Anonymous Chat Report - Category: {reason}"
            )
            await query.edit_message_text(f"Thank you! Your report for '{reason}' has been sent anonymously.")
            logger.info(f"Anonymous report received from {user_id} for reason: {reason}")
        except Exception as e:
            logger.error(f"Failed to send anonymous report from {user_id} for reason {reason}: {e}")
            await query.edit_message_text("There was an error sending your report. Please try again later.")
        
        # After sending report, ensure persistent reply keyboard is shown
        await context.bot.send_message(
            chat_id=user_id,
            text="You can find a new partner using the buttons below.",
            reply_markup=get_command_reply_keyboard()
        )
        return ConversationHandler.END

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ends the current chat and offers post-chat feedback."""
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        
        partner_id = None
        for uid, udata in user_data_store.items():
            if udata.get('match_id') == match_id and uid != user_id:
                partner_id = uid
                try:
                    await context.bot.send_message(chat_id=partner_id, text="Your partner has stopped the chat 😔\nUse the buttons below to find a new partner.")
                except Exception as e:
                    logger.warning(f"Could not notify partner {partner_id} about chat end: {e}")
                break
        
        # Clear match status for both users
        for uid, udata in user_data_store.items():
            if udata.get('match_id') == match_id:
                udata['in_search'] = False
                udata['match_id'] = None
                udata['last_active'] = datetime.now()

        await update.message.reply_text("You have stopped the chat. You are now out of the queue.")
        logger.info(f"Chat {match_id} stopped by user {user_id}.")
        
        # Offer post-chat feedback
        await update.message.reply_text(
            "If you wish, leave your feedback about your partner. It will help us find better partners for you in the future.",
            reply_markup=get_post_chat_feedback_keyboard()
        )
    else:
        await update.message.reply_text("You are not currently in a chat or searching. Use the buttons below to find a partner.")
        # Ensure main reply keyboard is shown
        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=get_command_reply_keyboard()
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides information on how to use the bot."""
    await update.message.reply_text(
        "Here's how to use The Secret Meet:\n\n"
        "**Persistent Buttons (bottom of chat):**\n"
        "• `🔍 Find a Match`: Search for a new chat partner.\n"
        "• `🛑 Stop Chat`: End your current chat with a partner.\n\n"
        "**Other Commands (type them out):**\n"
        "• `/start`: Begin your journey or return to the main menu.\n"
        "• `/help`: Get information on how to use the bot.\n"
        "• `/next`: (Same as 'Find a Match' button) Find a new partner.\n"
        "• `/stop`: (Same as 'Stop Chat' button) End your current chat.\n"
        "• `/sendfeedback`: Send general suggestions or comments directly to the bot owner.\n\n"
        "**During a chat:** Simply send any message (text, photos, videos, voice) and it will be forwarded anonymously to your partner.\n\n"
        "**After a chat:** You'll be prompted to give feedback (👍/👎) or report any issues (⚠️ Report) about your partner.",
        reply_markup=get_command_reply_keyboard() # Show persistent command keyboard after help
    )

async def send_match_found_message(user1_id, user2_id, application_bot):
    """Sends the 'Partner Found' message to both matched users."""
    match_id = uuid.uuid4()
    
    if user1_id in user_data_store:
        user_data_store[user1_id]['in_search'] = False
        user_data_store[user1_id]['match_id'] = match_id
    if user2_id in user_data_store:
        user_data_store[user2_id]['in_search'] = False
        user_data_store[user2_id]['match_id'] = match_id

    match_info_msg = (
        "🎉 Partner found! 🎉\n\n"
        "Say hello! 👋\n"
        "Use the buttons below:\n"
        "• `🛑 Stop Chat` — stop this chat\n"
        "• `🔍 Find a Match` — find a new partner"
    )

    try:
        # --- NEW: Send typing action for better UX ---
        await application_bot.send_chat_action(chat_id=user1_id, action=ChatAction.TYPING)
        await application_bot.send_chat_action(chat_id=user2_id, action=ChatAction.TYPING)
        await asyncio.sleep(1) # Small delay to make typing action visible

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
    """Periodically checks for and matches users in the search queue."""
    while True:
        await asyncio.sleep(1) # Reduced to 1 second for faster matching
        
        users_in_search = [
            user for user_id, user in user_data_store.items()
            if user["in_search"] and user["match_id"] is None
        ]
        
        if len(users_in_search) < 2:
            continue

        if len(users_in_search) >= 2:
            user1 = users_in_search[0]
            user2 = users_in_search[1]
            
            await send_match_found_message(user1['user_id'], user2['user_id'], application.bot)

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forwards messages anonymously between matched users, blocking specific content."""
    user_id = update.effective_user.id
    
    # Ignore messages that are commands or specific button texts handled by RegexHandler
    if update.message.text and (update.message.text.startswith('/') or update.message.text in ["🔍 Find a Match", "🛑 Stop Chat"]):
        return

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
                # --- Anonymity: No forward sign is ensured by re-sending content, not using forward_message. ---
                # --- Anonymity: Blocking contact cards. ---
                if update.message.contact:
                    await update.message.reply_text("Sharing contact information is not allowed to maintain anonymity.")
                    logger.warning(f"User {user_id} attempted to send a contact card to {partner_id}. Blocked for anonymity.")
                    return # Do not forward
                
                if update.message.text:
                    await context.bot.send_message(chat_id=partner_id, text=update.message.text)
                elif update.message.photo:
                    photo_file_id = update.message.photo[-1].file_id
                    await context.bot.send_photo(chat_id=partner_id, photo=photo_file_id, caption=update.message.caption)
                elif update.message.video:
                    video_file_id = update.message.video.file_id
                    await context.bot.send_video(chat_id=partner_id, video=video_file_id, caption=update.message.caption)
                elif update.message.voice:
                    voice_file_id = update.message.voice.file_id
                    await context.bot.send_voice(chat_id=partner_id, voice=voice_file_id, caption=update.message.caption)
                elif update.message.sticker:
                    sticker_file_id = update.message.sticker.file_id
                    await context.bot.send_sticker(chat_id=partner_id, sticker=sticker_file_id)
                elif update.message.animation:
                    animation_file_id = update.message.animation.file_id
                    await context.bot.send_animation(chat_id=partner_id, animation=animation_file_id, caption=update.message.caption)
                elif update.message.document:
                    document_file_id = update.message.document.file_id
                    await context.bot.send_document(chat_id=partner_id, document=document_file_id, caption=update.message.caption)
                elif update.message.audio:
                    audio_file_id = update.message.audio.file_id
                    await context.bot.send_audio(chat_id=partner_id, audio=audio_file_id, caption=update.message.caption)
                elif update.message.location:
                    await context.bot.send_location(
                        chat_id=partner_id, 
                        latitude=update.message.location.latitude, 
                        longitude=update.message.location.longitude
                    )
                else:
                    await update.message.reply_text("Sorry, this type of message cannot be sent anonymously.")
                    logger.warning(f"Unsupported message type from {user_id}: {update.message}")
                    return

                logger.info(f"Message content from {user_id} sent anonymously to {partner_id}.")
            except Exception as e:
                logger.error(f"Error sending anonymous message from {user_id} to {partner_id}: {e}")
                await update.message.reply_text("Could not send your message to your partner. They might have left or blocked the bot.")
                await stop_chat(update, context)
        else:
            await update.message.reply_text("You are not currently in a chat. Use the buttons below to find a partner.")
            await remove_user_from_search(user_id)
    else:
        await update.message.reply_text("You are not currently in a chat. Use the buttons below to find a partner.")

async def post_init_callback(application: Application) -> None:
    """Callback run after the bot starts, to set up background tasks and bot commands."""
    logger.info("Running post_init_callback (no database init).")
    application.bot_data['matching_scheduler_task'] = application.create_task(matching_scheduler(application))
    
    # Set bot commands for the '/' menu
    await application.bot.set_my_commands([
        ("start", "Start the bot or return to the main menu"),
        ("help", "Get information on how to use the bot"),
        ("next", "Find a new partner (same as Find a Match button)"),
        ("stop", "Stop your current chat (same as Stop Chat button)"),
        ("sendfeedback", "Send general feedback to the bot owner")
    ])
    logger.info("Bot commands set.")
    logger.info("post_init_callback finished.")

async def post_shutdown_callback(application: Application) -> None:
    """Callback run before the bot shuts down."""
    logger.info("Bot application shutting down (no database close).")
    pass

def main() -> None:
    """Starts the bot."""
    webhook_url = os.getenv("WEBHOOK_URL")

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init_callback).post_shutdown(post_shutdown_callback).build()

    # Main Conversation Handler (for /start, can be expanded for other flows)
    application.add_handler(CommandHandler("start", start))

    # General Feedback Conversation Handler (only accessible via command now)
    feedback_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("sendfeedback", send_feedback_start)],
        states={
            FEEDBACK_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback),
                CommandHandler("cancel", receive_feedback)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END 
        }
    )
    application.add_handler(feedback_conv_handler)

    # Report Conversation Handler (post-chat only, specific reasons)
    report_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(chat_feedback_report_start, pattern='^chat_feedback_report_start$')],
        states={}, # No states needed for simple category selection
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END 
        }
    )
    application.add_handler(report_conv_handler)

    # Command Handlers (for typing commands)
    application.add_handler(CommandHandler("stop", stop_chat))
    application.add_handler(CommandHandler("next", find_next_match_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Message Handlers for the persistent reply keyboard buttons
    application.add_handler(MessageHandler(filters.Regex("^🔍 Find a Match$"), find_next_match_command))
    application.add_handler(MessageHandler(filters.Regex("^🛑 Stop Chat$"), stop_chat))

    # Callback Query Handlers (for inline buttons, e.g., post-chat feedback/reports)
    application.add_handler(CallbackQueryHandler(handle_chat_feedback, pattern='^chat_feedback_(up|down)$'))
    application.add_handler(CallbackQueryHandler(handle_specific_report_reason, pattern='^report_reason_'))

    # Message handler to catch all text/media that is not a command or specific button text
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.Regex("^(🔍 Find a Match|🛑 Stop Chat)$"), forward_message))

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
