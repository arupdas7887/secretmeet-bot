import asyncio
import logging
import uuid
from datetime import datetime, timedelta
import os

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
# In-memory storage for blocked users: {user_id: datetime_of_expiration}
blocked_users = {}

# Conversation states
FEEDBACK_MESSAGE = 1
REPORT_REASON_SELECTION = 2 # New state for selecting report reasons

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
    # If user exists, ensure username/full_name are up-to-date
    else:
        user_data_store[user_id]["username"] = username
        user_data_store[user_id]["full_name"] = full_name
        user_data_store[user_id]["last_active"] = datetime.now() # Update last active
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

# Universal Block Check Function
async def is_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    
    # Clean up expired blocks
    expired_users = [uid for uid, expiry_time in blocked_users.items() if datetime.now() >= expiry_time]
    for uid in expired_users:
        del blocked_users[uid]
        logger.info(f"User {uid} block expired and removed from blocked_users.")

    if user_id in blocked_users:
        message_text = "You are temporarily blocked from using this bot for 24 hours due to a violation of our rules."
        if update.callback_query:
            await update.callback_query.answer(text=message_text, show_alert=True)
            # No edit_message_text here, just an alert.
        else:
            await update.message.reply_text(message_text)
        logger.info(f"Blocked user {user_id} attempted to interact with bot.")
        return True
    return False

# Utility functions for keyboards
def get_command_reply_keyboard():
    """Returns the persistent reply keyboard with Find Match and Stop Chat buttons."""
    keyboard = [
        [KeyboardButton("🔍 Find a Match")],
        [KeyboardButton("🛑 Stop Chat")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_post_chat_feedback_keyboard(reported_partner_id: int):
    """Returns the inline keyboard for post-chat feedback and reports."""
    keyboard = [
        [InlineKeyboardButton("👍", callback_data="chat_feedback_up"),
         InlineKeyboardButton("👎", callback_data="chat_feedback_down")],
        # Pass reported_partner_id to the report start callback
        [InlineKeyboardButton("⚠️ Report", callback_data=f"chat_feedback_report_start_{reported_partner_id}")]
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
    if await is_blocked(update, context):
        return ConversationHandler.END # Exit if blocked

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
    if await is_blocked(update, context):
        return # Exit if blocked

    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    # Ensure user data exists and retrieve it
    await create_user(user_id, username, full_name) 
    user_data = await get_user(user_id) # Fetch current user data

    if user_data and user_data.get('match_id'): # Check if user is already in a chat
        message_text = "You are already in a chat. Please stop your current chat first to find a new match."
        if update.callback_query:
            await update.callback_query.answer(text=message_text, show_alert=True)
        else:
            await update.message.reply_text(message_text, reply_markup=get_command_reply_keyboard())
        logger.info(f"User {user_id} attempted to find a match while already in chat {user_data['match_id']}.")
        return # Exit the function if already in a chat
    
    # If not in a chat, proceed with searching
    await update_user(user_id, in_search=True) 
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Searching for a partner now...")
    else:
        await update.message.reply_text("Searching for a partner now...")
    logger.info(f"User {user_id} initiated search.")

# General Feedback Handlers (only accessible via /sendfeedback command)
async def send_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the feedback conversation."""
    if await is_blocked(update, context):
        return ConversationHandler.END # Exit if blocked

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    else:
        await update.message.reply_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    return FEEDBACK_MESSAGE

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives and forwards general feedback to the admin."""
    if await is_blocked(update, context):
        return ConversationHandler.END # Exit if blocked

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
    if await is_blocked(update, context):
        return # Exit if blocked

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

async def chat_feedback_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the chat reporting process by showing reasons."""
    if await is_blocked(update, context):
        return ConversationHandler.END # Exit if blocked

    query = update.callback_query
    await query.answer()
    
    # Extract reported_partner_id from callback_data (e.g., "chat_feedback_report_start_12345")
    try:
        reported_partner_id = int(query.data.split('_')[-1])
        context.user_data['reported_partner_id'] = reported_partner_id # Store for later use
        logger.info(f"Reporter {query.from_user.id} initiating report for partner {reported_partner_id}.")
    except ValueError:
        logger.error(f"Invalid reported_partner_id in callback data: {query.data}")
        await query.edit_message_text("Error initiating report. Please try again.")
        return ConversationHandler.END

    await query.edit_message_text(
        "Choose a reason for your report:",
        reply_markup=get_report_reasons_keyboard()
    )
    return REPORT_REASON_SELECTION # Transition to the new state

async def handle_specific_report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of a specific report reason and sends it to the admin."""
    if await is_blocked(update, context):
        return ConversationHandler.END # Exit if blocked

    query = update.callback_query
    await query.answer() # Acknowledge callback immediately
    reporter_user_id = query.from_user.id
    reason = query.data.replace('report_reason_', '').replace('_', ' ').title()
    logger.info(f"User {reporter_user_id} selected report reason: {reason}") # Log the selected reason

    # Retrieve reported_partner_id from context.user_data
    reported_user_id = context.user_data.pop('reported_partner_id', None) # Remove it after use

    if reason == "Cancel":
        try:
            await query.edit_message_text(
                "Report cancelled.", # Minimal message for cancellation
                reply_markup=None # Remove inline keyboard, relying on persistent keyboard
            )
            logger.info(f"User {reporter_user_id} report cancelled. Message edited.")
        except Exception as e:
            logger.error(f"Error editing message for report cancellation for user {reporter_user_id}: {e}")
            # Fallback if editing fails: send a new message
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="Report cancelled, but there was an error updating the message.",
                reply_markup=get_command_reply_keyboard()
            )
        return ConversationHandler.END
    else: # It's a valid report reason
        if not reported_user_id:
            logger.error(f"No reported_partner_id found in context.user_data for report from {reporter_user_id}.")
            await query.edit_message_text("Error: Could not find reported partner's info. Please try again.", reply_markup=None)
            return ConversationHandler.END

        # Get reported user's details
        reported_user_info = await get_user(reported_user_id)
        reported_username = reported_user_info.get('username', 'N/A') if reported_user_info else 'N/A'
        reported_full_name = reported_user_info.get('full_name', 'N/A') if reported_user_info else 'N/A'

        # Get reporter's details
        reporter_user_info = await get_user(reporter_user_id)
        reporter_username = reporter_user_info.get('username', 'N/A') if reporter_user_info else 'N/A'
        reporter_full_name = reporter_user_info.get('full_name', 'N/A') if reporter_user_info else 'N/A'

        report_message_to_admin = (
            f"🚫 Chat Report 🚫\n"
            f"Category: {reason}\n\n"
            f"--- Reported Person ---\n"
            f"User ID: `{reported_user_id}`\n"
            f"Username: @{reported_username}\n"
            f"Full Name: {reported_full_name}\n\n"
            f"--- Reported By ---\n"
            f"User ID: `{reporter_user_id}`\n"
            f"Username: @{reporter_username}\n"
            f"Full Name: {reporter_full_name}"
        )
        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Block User for 24h", callback_data=f"admin_block_user:{reported_user_id}")]
        ])

        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=report_message_to_admin,
                reply_markup=admin_keyboard,
                parse_mode='Markdown' # For backticks around ID
            )
            logger.info(f"Report sent to admin from {reporter_user_id} for reason: {reason} (Reported: {reported_user_id}).")
            
            # Edit the existing inline message to a minimal acknowledgment and remove the keyboard for the reporter
            await query.edit_message_text(
                "Report sent.", # Minimal acknowledgment
                reply_markup=None # Remove the inline keyboard
            )
            logger.info(f"User {reporter_user_id} report sent. Message edited for reporter.")
        except Exception as e:
            logger.error(f"Failed to send report from {reporter_user_id} for reason {reason} (Reported: {reported_user_id}): {e}")
            # Fallback if sending or editing fails: send a new message to the reporter
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="There was an error sending your report or updating the message. Please try again later.",
                reply_markup=get_command_reply_keyboard()
            )

        return ConversationHandler.END

async def admin_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only callback to block a user for 24 hours."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    admin_id = query.from_user.id
    if admin_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized attempt to block user by {admin_id}.")
        return

    try:
        user_id_to_block = int(query.data.split(':')[-1])
        expiration_time = datetime.now() + timedelta(hours=24)
        blocked_users[user_id_to_block] = expiration_time
        logger.info(f"Admin {admin_id} blocked user {user_id_to_block} until {expiration_time}.")

        # Fetch blocked user's details for confirmation message
        blocked_user_info = await get_user(user_id_to_block)
        blocked_username = blocked_user_info.get('username', 'N/A') if blocked_user_info else 'N/A'
        blocked_full_name = blocked_user_info.get('full_name', 'N/A') if blocked_user_info else 'N/A'

        confirmation_message = (
            f"User blocked for 24 hours:\n"
            f"ID: `{user_id_to_block}`\n"
            f"Username: @{blocked_username}\n"
            f"Full Name: {blocked_full_name}\n"
            f"Will unblock automatically at {expiration_time.strftime('%Y-%m-%d %H:%M:%S')} IST."
        )
        await query.edit_message_text(
            text=confirmation_message,
            parse_mode='Markdown',
            reply_markup=None # Remove the block button from the report to prevent re-blocking
        )
    except Exception as e:
        logger.error(f"Error blocking user by admin {admin_id}: {e}")
        await query.edit_message_text("Error blocking user. Please check logs.")


async def end_chat_for_users(user1_id: int, user2_id: int, application_bot: Application, initiator_id: int = None) -> None:
    """Ends the chat for both users and offers feedback.
    initiator_id: The ID of the user who explicitly stopped the chat, if any."""
    
    # Clean up expired blocks for users involved in chat end
    for user_id_check in [user1_id, user2_id]:
        if user_id_check in blocked_users and datetime.now() >= blocked_users[user_id_check]:
            del blocked_users[user_id_check]
            logger.info(f"User {user_id_check} block expired at chat end.")

    is_user1_blocked = user1_id in blocked_users
    is_user2_blocked = user2_id in blocked_users

    if initiator_id: # The one who explicitly stopped
        initiator_text = "You have stopped the chat. You are now out of the queue."
        partner_text = "Your partner has stopped the chat 😔\nUse the buttons below to find a new partner."
    else: # If chat ended for other reasons (e.g., disconnection, error, or not explicitly stopped)
        initiator_text = "Your chat has ended. You are now out of the queue."
        partner_text = "Your chat has ended. You are now out of the queue."

    # Clear match status for both users
    for user_id in [user1_id, user2_id]:
        if user_id in user_data_store:
            user_data_store[user_id]['in_search'] = False
            user_data_store[user_id]['match_id'] = None
            user_data_store[user_id]["last_active"] = datetime.now()

    try:
        # Send distinct messages based on initiator, only if not blocked
        if initiator_id == user1_id:
            if not is_user1_blocked:
                await application_bot.bot.send_message(chat_id=user1_id, text=initiator_text)
            if not is_user2_blocked:
                await application_bot.bot.send_message(chat_id=user2_id, text=partner_text)
        elif initiator_id == user2_id:
            if not is_user2_blocked:
                await application_bot.bot.send_message(chat_id=user2_id, text=initiator_text)
            if not is_user1_blocked:
                await application_bot.bot.send_message(chat_id=user1_id, text=partner_text)
        else: # No specific initiator (e.g., error in forwarding)
            if not is_user1_blocked:
                await application_bot.bot.send_message(chat_id=user1_id, text=initiator_text)
            if not is_user2_blocked:
                await application_bot.bot.send_message(chat_id=user2_id, text=partner_text)

        # Send feedback option to BOTH users, but only if not blocked
        feedback_msg = "If you wish, leave your feedback about your partner. It will help us find better partners for you in the future."
        
        # Ensure reported_partner_id is correct for each feedback message
        if not is_user1_blocked:
            await application_bot.bot.send_message(
                chat_id=user1_id,
                text=feedback_msg,
                reply_markup=get_post_chat_feedback_keyboard(reported_partner_id=user2_id) # Reporter user1, reported user2
            )
        if not is_user2_blocked:
            await application_bot.bot.send_message(
                chat_id=user2_id,
                text=feedback_msg,
                reply_markup=get_post_chat_feedback_keyboard(reported_partner_id=user1_id) # Reporter user2, reported user1
            )
        logger.info(f"Chat ended for {user1_id} and {user2_id}. Feedback offered (to unblocked users).")

    except Exception as e:
        logger.error(f"Error ending chat or offering feedback for {user1_id}, {user2_id}: {e}")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ends the current chat and offers post-chat feedback to both participants."""
    if await is_blocked(update, context):
        return # Exit if blocked

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
            await end_chat_for_users(user_id, partner_id, context.application, initiator_id=user_id)
            logger.info(f"Chat {match_id} stopped by user {user_id}.")
        else:
            # User had a match_id, but partner was not found (e.g., partner's state cleared, bot restarted)
            await remove_user_from_search(user_id) # Clear initiator's state
            await update.message.reply_text("You have left your previous conversation. Your partner may have disconnected.", reply_markup=get_command_reply_keyboard())
            # Offer feedback specifically to the initiator, as partner is unknown or state is inconsistent
            feedback_msg = "If you wish, you can still leave feedback about your last interaction."
            try:
                # Use a dummy ID (e.g., 0) for reported_partner_id if truly unknown, but better to avoid this path
                # if possible by ensuring partner_id is always resolved before offering report.
                # For robustness, using 0 and handling it in report handlers is an option.
                await context.bot.send_message(
                    chat_id=user_id,
                    text=feedback_msg,
                    reply_markup=get_post_chat_feedback_keyboard(reported_partner_id=0) # Dummy ID for unknown partner
                )
                logger.info(f"User {user_id} stopped chat with missing partner. Feedback offered to initiator.")
            except Exception as e:
                logger.error(f"Error offering feedback to {user_id} after partner missing: {e}")
    else:
        await update.message.reply_text("You are not currently in a chat or searching. Use the buttons below to find a partner.", reply_markup=get_command_reply_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides information on how to use the bot."""
    if await is_blocked(update, context):
        return # Exit if blocked

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
        "**After a chat:** You'll be prompted to give feedback (👍/👎) or report any issues (⚠️ Report) about your partner.\n\n"
        "**Admin Commands (for bot owner only):**\n"
        "• `/unblock <user_id>`: Manually unblock a user by their ID.\n"
        "• `🚫 Block User for 24h` button (in reports): Temporarily block a reported user.",
        reply_markup=get_command_reply_keyboard() # Show persistent command keyboard after help
    )

async def send_match_found_message(user1_id, user2_id, application_bot):
    """Sends the 'Partner Found' message to both matched users and shows typing."""
    # Check if any user became blocked during the search process
    if user1_id in blocked_users and datetime.now() < blocked_users[user1_id]:
        logger.info(f"User {user1_id} found match but is blocked. Not sending message.")
        return
    if user2_id in blocked_users and datetime.now() < blocked_users[user2_id]:
        logger.info(f"User {user2_id} found match but is blocked. Not sending message.")
        return

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
        # Send match found message first
        await application_bot.send_message(chat_id=user1_id, text=match_info_msg) 
        await application_bot.send_message(chat_id=user2_id, text=match_info_msg)
        
        # Then send typing action. This will make it appear as if the other user is typing.
        await application_bot.send_chat_action(chat_id=user1_id, action=ChatAction.TYPING) # User1 sees typing from User2
        await application_bot.send_chat_action(chat_id=user2_id, action=ChatAction.TYPING) # User2 sees typing from User1
        # No sleep needed here, the typing indicator will naturally disappear after a few seconds
        # or when an actual message is sent.

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
        
        # Filter out blocked users from the search queue
        users_in_search = [
            user for user_id, user in user_data_store.items()
            if user["in_search"] and user["match_id"] is None and \
               (user_id not in blocked_users or datetime.now() >= blocked_users[user_id])
        ]
        
        if len(users_in_search) < 2:
            continue

        if len(users_in_search) >= 2:
            user1 = users_in_search[0]
            user2 = users_in_search[1]
            
            await send_match_found_message(user1['user_id'], user2['user_id'], application.bot)

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forwards messages anonymously between matched users, blocking specific content."""
    if await is_blocked(update, context):
        return # Exit if blocked

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
            # Check if partner is blocked
            if partner_id in blocked_users and datetime.now() < blocked_users[partner_id]:
                await update.message.reply_text("Your partner has been temporarily blocked and cannot receive messages.")
                logger.info(f"User {user_id} tried to send message to blocked partner {partner_id}.")
                # End chat for the non-blocked user, as communication is broken
                await end_chat_for_users(user_id, partner_id, context.application, initiator_id=None) # Bot initiated stop
                return

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
                await end_chat_for_users(user_id, partner_id, context.application) 
        else:
            await update.message.reply_text("You are not currently in a chat. Use the buttons below to find a partner.")
            await remove_user_from_search(user_id)
    else:
        await update.message.reply_text("You are not currently in a chat. Use the buttons below to find a partner.")

async def post_init_callback(application: Application) -> None:
    """Callback run after the bot starts, to set up background tasks and bot commands."""
    logger.info("Running post_init_callback (no database init).")
    application.bot_data['matching_scheduler_task'] = application.create_task(matching_scheduler(application))
    
    # Set bot commands for the '/' menu (Removed /sendfeedback as requested)
    await application.bot.set_my_commands([
        ("start", "Start the bot or return to the main menu"),
        ("help", "Get information on how to use the bot"),
        ("next", "Find a new partner (same as Find a Match button)"),
        ("stop", "Stop your current chat (same as Stop Chat button)"),
        ("unblock", "Admin: Unblock a user by ID") # Added for admin unblock capability
    ])
    logger.info("Bot commands set.")
    logger.info("post_init_callback finished.")

async def post_shutdown_callback(application: Application) -> None:
    """Callback run before the bot shuts down."""
    logger.info("Bot application shutting down (no database close).")
    pass

async def admin_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to manually unblock a user."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized attempt to unblock user by {update.effective_user.id}.")
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /unblock <user_id>")
        return

    user_id_to_unblock = int(context.args[0])
    if user_id_to_unblock in blocked_users:
        del blocked_users[user_id_to_unblock]
        await update.message.reply_text(f"User `{user_id_to_unblock}` has been unblocked manually.")
        logger.info(f"Admin {update.effective_user.id} manually unblocked user {user_id_to_unblock}.")
    else:
        await update.message.reply_text(f"User `{user_id_to_unblock}` is not currently blocked.")
    await update.message.reply_text(f"Current blocked users: {list(blocked_users.keys())}")


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
        entry_points=[CallbackQueryHandler(chat_feedback_report_start, pattern=r'^chat_feedback_report_start_\d+$')], # Regex to match ID
        states={
            REPORT_REASON_SELECTION: [ # This is the state where report reasons are selected
                CallbackQueryHandler(handle_specific_report_reason, pattern='^report_reason_')
            ]
        },
        fallbacks=[CommandHandler("start", start)], # If in report flow and user types /start
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END 
        }
    )
    application.add_handler(report_conv_handler)

    # Command Handlers (for typing commands)
    application.add_handler(CommandHandler("stop", stop_chat))
    application.add_handler(CommandHandler("next", find_next_match_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("unblock", admin_unblock_user)) # Admin unblock command
    
    # Message Handlers for the persistent reply keyboard buttons
    application.add_handler(MessageHandler(filters.Regex("^🔍 Find a Match$"), find_next_match_command))
    application.add_handler(MessageHandler(filters.Regex("^🛑 Stop Chat$"), stop_chat))

    # Callback Query Handlers (for inline buttons, e.g., post-chat feedback/reports)
    application.add_handler(CallbackQueryHandler(handle_chat_feedback, pattern='^chat_feedback_(up|down)$'))
    application.add_handler(CallbackQueryHandler(admin_block_user, pattern=r'^admin_block_user:\d+$')) # Admin block callback

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
