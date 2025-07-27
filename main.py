import asyncio
import logging
import uuid
from datetime import datetime, timedelta
import os
import json

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

# --- Firestore Imports ---
import firebase_admin
from firebase_admin import credentials
import google.cloud.firestore
from google.cloud.firestore import FieldFilter

# --- Configuration ---
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk" # IMPORTANT: Confirm this is your actual Bot Token
ADMIN_USER_ID = 5246076255 # IMPORTANT: Replace with your actual Telegram User ID!

# --- Enable logging (MOVED TO HERE) ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Firestore Setup ---
# Initialize Firebase Admin SDK
db = None # Will be initialized
if not firebase_admin._apps:
    try:
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            # For Render deployment using the entire JSON string as an environment variable
            cred_dict = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
            cred = credentials.Certificate(cred_dict)
            logger.info("Firebase credentials loaded from GOOGLE_APPLICATION_CREDENTIALS_JSON environment variable.")
        elif os.path.exists("service-account-key.json"): # For local testing (ensure this file exists)
            cred = credentials.Certificate("service-account-key.json")
            logger.info("Firebase credentials loaded from service-account-key.json file.")
        else:
            raise Exception("Firebase credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS_JSON env var or place 'service-account-key.json' file.")

        firebase_admin.initialize_app(cred)
        db = google.cloud.firestore.Client()
        logger.info("Firestore client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firestore: {e}")
        # In a real bot, you might want to exit or log a critical error.
        # For now, `db` remains None and subsequent DB operations will fail.

users_collection = db.collection('users') if db else None

# In-memory storage for blocked users: {user_id: datetime_of_expiration}
# IMPORTANT: This is NOT persistent across bot restarts. For persistence, move to Firestore.
blocked_users = {}


# Conversation states
FEEDBACK_MESSAGE = 1
REPORT_REASON_SELECTION = 2
SUPPORT_MESSAGE = 3

# --- User Data Operations (Firestore-based) ---
async def get_user(user_id: int):
    """Retrieves user data from Firestore."""
    if not db: return None # Handle uninitialized db
    try:
        doc_ref = db.collection('users').document(str(user_id))
        doc = await doc_ref.get_async()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Error getting user {user_id} from Firestore: {e}")
        return None

async def create_or_update_user(user_id: int, username: str, full_name: str):
    """Creates or updates user data in Firestore, including new gender/referral fields."""
    if not db: return False # Handle uninitialized db
    try:
        user_ref = db.collection('users').document(str(user_id))
        
        # Check if user exists to decide on setting 'created_at' and default new fields
        doc = await user_ref.get_async()
        
        user_data = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "last_active": datetime.now(),
            "updated_at": datetime.now()
        }
        
        if not doc.exists:
            user_data["created_at"] = datetime.now()
            user_data["in_search"] = False
            user_data["match_id"] = None
            user_data["is_matching"] = False # Ensure this is also initialized
            user_data["referral_count"] = 0 # New field
            user_data["gender_feature_unlocked_at"] = None # New field
            user_data["user_gender"] = None # New field
            user_data["looking_for_gender"] = None # New field
            user_data["current_bot_state"] = None # New field for conversation state
            user_data["search_type"] = None # New field: 'general', 'gender_specific'
            logger.info(f"New user {user_id} created in Firestore.")
        else:
            logger.info(f"User {user_id} updated in Firestore.")
        
        await user_ref.set(user_data, merge=True) # Use set with merge=True
        return True
    except Exception as e:
        logger.error(f"Error creating/updating user {user_id} in Firestore: {e}")
        return False

async def update_user_field(user_id: int, **kwargs):
    """Updates specific fields for a user in Firestore."""
    if not db: return False # Handle uninitialized db
    try:
        user_ref = db.collection('users').document(str(user_id))
        kwargs["last_active"] = datetime.now()
        kwargs["updated_at"] = datetime.now()
        await user_ref.update(kwargs)
        logger.info(f"User {user_id} fields updated in Firestore: {kwargs}.")
        return True
    except Exception as e:
        logger.error(f"Error updating user {user_id} fields in Firestore: {e}")
        return False

async def remove_user_from_search(user_id: int):
    """Clears search status for a user in Firestore."""
    return await update_user_field(user_id, in_search=False, match_id=None, is_matching=False, search_type=None, current_bot_state=None)

# Universal Block Check Function (assuming blocked_users remains in-memory for now)
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
        else:
            await update.message.reply_text(message_text)
        logger.info(f"Blocked user {user_id} attempted to interact with bot.")
        return True
    return False

# --- Utility functions for keyboards ---

def get_command_reply_keyboard():
    """Returns the main ReplyKeyboardMarkup for commands, including new gender search."""
    keyboard = [
        [KeyboardButton("🔍 Find a Match")],
        [KeyboardButton("🛑 Stop Chat")],
        [KeyboardButton("👫 Search by Gender")] # New button
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_post_chat_feedback_keyboard(reported_partner_id: int):
    """Returns the inline keyboard for post-chat feedback."""
    keyboard = [
        [InlineKeyboardButton("👍", callback_data="chat_feedback_up"),
         InlineKeyboardButton("👎", callback_data="chat_feedback_down")],
        [InlineKeyboardButton("⚠️ Report", callback_data=f"chat_feedback_report_start_{reported_partner_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_report_reasons_keyboard():
    """Returns the inline keyboard for report reasons."""
    keyboard = [
        [InlineKeyboardButton("Spam / Advertising", callback_data="report_reason_spam")],
        [InlineKeyboardButton("Harassment / Abuse", callback_data="report_reason_harassment")],
        [InlineKeyboardButton("Inappropriate Content", callback_data="report_reason_inappropriate")],
        [InlineKeyboardButton("← Back", callback_data="report_reason_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_own_gender_inline_keyboard():
    """Returns the inline keyboard for user's own gender selection (Male/Female/Other)."""
    keyboard = [
        [
            InlineKeyboardButton("Male", callback_data="gender_male"),
            InlineKeyboardButton("Female", callback_data="gender_female")
        ],
        [
            InlineKeyboardButton("Other", callback_data="gender_other")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_looking_for_gender_inline_keyboard():
    """Returns the inline keyboard for preferred gender for match selection (Male/Female/Other/Any)."""
    keyboard = [
        [
            InlineKeyboardButton("Male", callback_data="looking_for_gender_male"),
            InlineKeyboardButton("Female", callback_data="looking_for_gender_female")
        ],
        [
            InlineKeyboardButton("Other", callback_data="looking_for_gender_other"),
            InlineKeyboardButton("Any Gender", callback_data="looking_for_gender_any")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /start command, creates/updates user, and shows main keyboard."""
    if await is_blocked(update, context):
        return ConversationHandler.END # If using ConversationHandler for start

    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    await create_or_update_user(user_id, username, full_name)
    
    await update.message.reply_text(
        f"Welcome to The Secret Meet, {full_name}! Use the buttons below to find a match or type /help.",
        reply_markup=get_command_reply_keyboard(),
    )
    return ConversationHandler.END # Or return a state if start is part of a conversation

async def find_next_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates the search for a new partner (general search)."""
    if await is_blocked(update, context):
        return

    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data.get('is_matching'): # Check 'is_matching' as it means active chat
        message_text = "You are already in a chat. Please stop your current chat first to find a new match."
        if update.callback_query:
            await update.callback_query.answer(text=message_text, show_alert=True)
        else:
            await update.message.reply_text(message_text, reply_markup=get_command_reply_keyboard())
        logger.info(f"User {user_id} attempted to find a match while already in chat {user_data.get('match_id')}.")
        return
    
    # If not in search or matching, update to 'in_search'
    await update_user_field(user_id, in_search=True, search_type='general', match_id=None, is_matching=False, current_bot_state=None)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Searching for a partner now...")
    else:
        await update.message.reply_text("Searching for a partner now...")
    logger.info(f"User {user_id} initiated general search.")

async def stop_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Stop Chat' button, ending current chat or search."""
    if await is_blocked(update, context):
        return

    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if not user_data:
        await update.message.reply_text("Please /start the bot first.")
        return

    partner_id = user_data.get('match_id')

    # Update current user's status
    await update_user_field(user_id, in_search=False, is_matching=False, match_id=None, search_type=None, current_bot_state=None)
    
    await update.message.reply_text("You have stopped the chat/search.", reply_markup=get_command_reply_keyboard())
    logger.info(f"User {user_id} stopped chat/search.")

    if partner_id:
        partner_ref = users_collection.document(str(partner_id))
        partner_data_doc = await partner_ref.get_async()
        if partner_data_doc.exists and partner_data_doc.to_dict().get('match_id') == user_id:
            # Update partner's status if they were still matched with this user
            await update_user_field(partner_id, in_search=False, is_matching=False, match_id=None, search_type=None, current_bot_state=None)
            await context.bot.send_message(
                chat_id=partner_id,
                text="Your partner has disconnected. You can find a new partner using the buttons below.",
                reply_markup=get_command_reply_keyboard()
            )
            # Send feedback keyboard to partner
            await context.bot.send_message(
                chat_id=partner_id,
                text="How was your chat with this user?",
                reply_markup=get_post_chat_feedback_keyboard(reported_partner_id=user_id)
            )
            logger.info(f"Chat between {user_id} and {partner_id} ended by {user_id}.")
        else:
            logger.info(f"User {user_id} stopped, but partner {partner_id} was already disconnected or not matched mutually.")
    else:
        logger.info(f"User {user_id} stopped search, not in active chat.")


# --- New "Search by Gender" Handlers ---

async def search_by_gender_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Search by Gender' button click."""
    if await is_blocked(update, context):
        return

    user_id = str(update.effective_user.id)
    user_ref = users_collection.document(user_id)
    user_data_doc = await user_ref.get_async()
    user_data = user_data_doc.to_dict()

    if not user_data:
        await update.message.reply_text("Please /start the bot first to initialize your profile.")
        return
    
    # If user is already in a match, stop it first
    if user_data.get('is_matching'):
        await stop_chat_command(update, context) # Use existing stop logic
        await update.message.reply_text("Please click 'Search by Gender' again after the current chat is stopped.")
        return

    referral_count = user_data.get('referral_count', 0)
    gender_feature_unlocked_at = user_data.get('gender_feature_unlocked_at')

    is_eligible = False
    if referral_count >= 3 and gender_feature_unlocked_at:
        if isinstance(gender_feature_unlocked_at, google.cloud.firestore.Timestamp):
            unlocked_at_dt = gender_feature_unlocked_at.astimezone(datetime.timezone.utc)
        elif isinstance(gender_feature_unlocked_at, datetime): # Direct datetime from local test or old data
             unlocked_at_dt = gender_feature_unlocked_at.astimezone(datetime.timezone.utc)
        else:
            unlocked_at_dt = None # Invalid or missing timestamp
            
        if unlocked_at_dt:
            time_elapsed = datetime.now(datetime.timezone.utc) - unlocked_at_dt
            if time_elapsed < timedelta(hours=3):
                is_eligible = True
            else:
                logger.info(f"User {user_id}: Gender feature 3-hour window expired.")
                await user_ref.update({'gender_feature_unlocked_at': None}) # Reset for next unlock
    
    if not is_eligible:
        message = (
            f"You can only use this feature when you refer 3 people. "
            f"Once unlocked, you can use this feature for 3 hours. "
            f"You have currently referred {referral_count} people."
        )
        await update.message.reply_text(message, reply_markup=get_command_reply_keyboard())
        logger.info(f"User {user_id} tried gender search, but not eligible (referrals: {referral_count}).")
    else:
        logger.info(f"User {user_id} is eligible for gender search.")
        user_gender = user_data.get('user_gender')
        if not user_gender:
            await update.message.reply_text(
                "First, what is your gender?",
                reply_markup=get_own_gender_inline_keyboard()
            )
            await user_ref.update({'current_bot_state': 'awaiting_own_gender'})
            logger.info(f"User {user_id} asked for own gender.")
        else:
            await update.message.reply_text(
                "Which gender are you looking to chat with?",
                reply_markup=get_looking_for_gender_inline_keyboard()
            )
            await user_ref.update({'current_bot_state': 'awaiting_looking_for_gender'})
            logger.info(f"User {user_id} asked for looking for gender.")

async def gender_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline keyboard button presses for gender selection."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query to remove loading state
    user_id = str(query.from_user.id)
    user_ref = users_collection.document(user_id)
    user_data_doc = await user_ref.get_async()
    user_data = user_data_doc.to_dict()

    if not user_data:
        await query.message.reply_text("Please /start the bot first.")
        return

    current_bot_state = user_data.get('current_bot_state')

    if query.data.startswith('gender_') and current_bot_state == 'awaiting_own_gender':
        selected_gender = query.data.replace('gender_', '')
        await user_ref.update({'user_gender': selected_gender})
        await query.edit_message_text(f"Your gender set to: {selected_gender.capitalize()}")
        logger.info(f"User {user_id} set own gender to: {selected_gender}.")

        # Now ask for preferred gender for match
        await query.message.reply_text(
            "Which gender are you looking to chat with?",
            reply_markup=get_looking_for_gender_inline_keyboard()
        )
        await user_ref.update({'current_bot_state': 'awaiting_looking_for_gender'})
        logger.info(f"User {user_id} moved to looking for gender.")

    elif query.data.startswith('looking_for_gender_') and current_bot_state == 'awaiting_looking_for_gender':
        selected_preference = query.data.replace('looking_for_gender_', '')
        await user_ref.update({
            'looking_for_gender': selected_preference,
            'in_search': True,
            'search_type': 'gender_specific', # Mark search as gender-specific
            'current_bot_state': None # Clear state
        })
        await query.edit_message_text(f"You are looking for: {selected_preference.replace('_', ' ').capitalize()}")
        await query.message.reply_text(
            f"Okay, you are looking for a {selected_preference.replace('_', ' ')} partner. Searching for a match now...",
            reply_markup=get_command_reply_keyboard() # Show main keyboard again
        )
        logger.info(f"User {user_id} set looking for gender to: {selected_preference}. Initiating gender-specific search.")

        # --- Trigger Matching Logic (Conceptual) ---
        # If your matching scheduler runs very frequently, it will pick this up.
        # Otherwise, you might want to directly call a matching function here.

    else:
        # Handle unexpected callback data or state mismatch
        await query.message.reply_text("An error occurred or your previous action timed out. Please try again or use /start.", reply_markup=get_command_reply_keyboard())
        logger.warning(f"User {user_id} received unexpected callback data: {query.data} in state {current_bot_state}")

# --- General Feedback Handlers ---
async def send_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    if update.callback_query: # This might be from a keyboard button
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    else: # This might be from a /feedback command
        await update.message.reply_text("Please type and send your general feedback message. You can type /cancel to go back to the main menu at any time.")
    return FEEDBACK_MESSAGE

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    if feedback_text and feedback_text.lower() == "/cancel":
        await update.message.reply_text(
            "Feedback cancelled.",
            reply_markup=get_command_reply_keyboard()
        )
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"Anonymous General Feedback:\n\nFrom User ID: `{user_id}`\nFeedback:\n{feedback_text}",
            parse_mode='Markdown'
        )
        await update.message.reply_text("Thank you for your feedback! It has been sent anonymously.", reply_markup=get_command_reply_keyboard())
        logger.info(f"Anonymous feedback received from {user_id} and forwarded to admin.")
    except Exception as e:
        logger.error(f"Failed to forward anonymous feedback from {user_id} to admin {ADMIN_USER_ID}: {e}")
        await update.message.reply_text("There was an error sending your feedback. Please try again later.", reply_markup=get_command_reply_keyboard())

    return ConversationHandler.END

# --- Support Chat Handlers ---
async def start_support_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    await update.message.reply_text(
        "Please type and send your support message. We will get back to you as soon as possible. Type /cancel to go back to the main menu."
    )
    return SUPPORT_MESSAGE

async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else "N/A"
    full_name = update.effective_user.full_name
    support_text = update.message.text

    if support_text and support_text.lower() == "/cancel":
        await update.message.reply_text(
            "Support request cancelled.",
            reply_markup=get_command_reply_keyboard()
        )
        return ConversationHandler.END

    support_message_to_admin = (
        f"🚨 New Support Request 🚨\n\n"
        f"From User ID: `{user_id}`\n"
        f"Username: @{username}\n"
        f"Full Name: {full_name}\n\n"
        f"Message:\n{support_text}\n\n"
        f"To reply to this user, use: `/reply {user_id} <your_message>`"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=support_message_to_admin,
            parse_mode='Markdown'
        )
        await update.message.reply_text(
            "Your support message has been sent. We will get back to you shortly.",
            reply_markup=get_command_reply_keyboard()
        )
        logger.info(f"Support request from {user_id} forwarded to admin.")
    except Exception as e:
        logger.error(f"Failed to forward support message from {user_id} to admin {ADMIN_USER_ID}: {e}")
        await update.message.reply_text(
            "There was an error sending your support message. Please try again later.",
            reply_markup=get_command_reply_keyboard()
        )

    return ConversationHandler.END

# --- Admin Reply Command ---
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    if admin_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized attempt to reply by {admin_id}.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/reply <user_id> <your_message>`", parse_mode='Markdown')
        return

    try:
        target_user_id = int(context.args[0])
        reply_message = " ".join(context.args[1:])

        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Admin Reply:\n\n{reply_message}"
        )
        await update.message.reply_text(f"Your reply has been sent to user `{target_user_id}`.", parse_mode='Markdown')
        logger.info(f"Admin {admin_id} replied to user {target_user_id}.")
    except ValueError:
        await update.message.reply_text("Invalid User ID. Please provide a numeric User ID.")
    except Exception as e:
        logger.error(f"Error sending reply from admin {admin_id} to user {target_user_id}: {e}")
        await update.message.reply_text(f"Failed to send reply to user `{target_user_id}`. Error: {e}", parse_mode='Markdown')

# --- Post-Chat Feedback Handlers ---
async def handle_chat_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await is_blocked(update, context):
        return

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    feedback_type = query.data.split('_')[-1]

    if feedback_type == 'up':
        await query.edit_message_text("👍 Thanks for your positive feedback!")
    elif feedback_type == 'down':
        await query.edit_message_text("👎 Sorry to hear that. We'll try to improve your matches.")
    
    # Send main keyboard after feedback
    await context.bot.send_message(
        chat_id=user_id,
        text="You can find a new partner using the buttons below.",
        reply_markup=get_command_reply_keyboard()
    )
    logger.info(f"User {user_id} gave chat feedback: {feedback_type}.")

async def chat_feedback_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    
    try:
        reported_partner_id = int(query.data.split('_')[-1])
        context.user_data['reported_partner_id'] = reported_partner_id
        logger.info(f"Reporter {query.from_user.id} initiating report for partner {reported_partner_id}.")
    except ValueError:
        logger.error(f"Invalid reported_partner_id in callback data: {query.data}")
        await query.edit_message_text("Error initiating report. Please try again.")
        return ConversationHandler.END

    await query.edit_message_text(
        "Choose a reason for your report:",
        reply_markup=get_report_reasons_keyboard()
    )
    return REPORT_REASON_SELECTION

async def handle_specific_report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await is_blocked(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    reporter_user_id = query.from_user.id
    reason = query.data.replace('report_reason_', '').replace('_', ' ').title()
    logger.info(f"User {reporter_user_id} selected report reason: {reason}")

    reported_user_id = context.user_data.pop('reported_partner_id', None)

    if reason == "Cancel": # This means "report_reason_cancel" callback
        try:
            await query.edit_message_text(
                "Report cancelled.",
                reply_markup=None # Remove inline keyboard
            )
            # Send main keyboard back to user
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="You can find a new partner using the buttons below.",
                reply_markup=get_command_reply_keyboard()
            )
            logger.info(f"User {reporter_user_id} report cancelled. Message edited.")
        except Exception as e:
            logger.error(f"Error editing message for report cancellation for user {reporter_user_id}: {e}")
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="Report cancelled, but there was an error updating the message.",
                reply_markup=get_command_reply_keyboard()
            )
        return ConversationHandler.END
    else:
        if not reported_user_id:
            logger.error(f"No reported_partner_id found in context.user_data for report from {reporter_user_id}.")
            await query.edit_message_text("Error: Could not find reported partner's info. Please try again.", reply_markup=None)
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="Please try again to report using the chat feedback option.",
                reply_markup=get_command_reply_keyboard()
            )
            return ConversationHandler.END

        # Get reported user's details from Firestore
        reported_user_info = await get_user(reported_user_id)
        reported_username = reported_user_info.get('username', 'N/A') if reported_user_info else 'N/A'
        reported_full_name = reported_user_info.get('full_name', 'N/A') if reported_user_info else 'N/A'

        # Get reporter's details from Firestore
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
                parse_mode='Markdown'
            )
            logger.info(f"Report sent to admin from {reporter_user_id} for reason: {reason} (Reported: {reported_user_id}).")
            
            await query.edit_message_text(
                "Report sent. We will review it shortly.",
                reply_markup=None # Remove inline keyboard
            )
            # Send main keyboard back to user
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="You can find a new partner using the buttons below.",
                reply_markup=get_command_reply_keyboard()
            )
            logger.info(f"User {reporter_user_id} report sent. Message edited for reporter.")
        except Exception as e:
            logger.error(f"Failed to send report from {reporter_user_id} for reason {reason} (Reported: {reported_user_id}): {e}")
            await context.bot.send_message(
                chat_id=reporter_user_id,
                text="There was an error sending your report or updating the message. Please try again later.",
                reply_markup=get_command_reply_keyboard()
            )

        return ConversationHandler.END

async def admin_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to block a user for 24 hours."""
    if await is_blocked(update, context): # Admin might also be blocked, although unlikely for this action
        return

    query = update.callback_query
    await query.answer()

    admin_id = query.from_user.id
    if admin_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized attempt to block user by {admin_id}.")
        return

    try:
        user_id_to_block = int(query.data.split(':')[-1])
        expiration_time = datetime.now() + timedelta(hours=24)
        blocked_users[user_id_to_block] = expiration_time # Store in memory for immediate access
        
        # Optionally, persist this block to Firestore as well for cross-instance consistency
        # await users_collection.document(str(user_id_to_block)).update({'blocked_until': expiration_time})

        await query.edit_message_text(f"User `{user_id_to_block}` has been blocked for 24 hours.", parse_mode='Markdown')
        logger.info(f"Admin {admin_id} blocked user {user_id_to_block} until {expiration_time}.")
        
        # Inform the blocked user (optional but good practice)
        try:
            await context.bot.send_message(
                chat_id=user_id_to_block,
                text="You have been temporarily blocked from using this bot for 24 hours due to a violation of our rules. If you believe this is an error, please contact support."
            )
        except Exception as e:
            logger.warning(f"Could not inform blocked user {user_id_to_block} about block: {e}")

    except ValueError:
        await query.edit_message_text("Invalid User ID in callback data.")
    except Exception as e:
        logger.error(f"Error blocking user from admin {admin_id}: {e}")
        await query.edit_message_text(f"Failed to block user. Error: {e}")


# --- Message Forwarding Logic (Conceptual - IMPORTANT: Implement this based on your needs) ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forwards messages between matched users."""
    if await is_blocked(update, context):
        return

    user_id = str(update.effective_user.id)
    user_data = await get_user(user_id)

    if not user_data or not user_data.get('is_matching'):
        # If user is not in an active chat, don't forward messages.
        # Could reply with instructions or ignore.
        # await update.message.reply_text("You are not currently in a chat. Use 'Find a Match' to start.")
        logger.info(f"User {user_id} sent message while not in chat: {update.message.text}")
        return

    partner_id = user_data.get('match_id')

    if partner_id:
        try:
            # Forward the message to the partner
            await update.effective_message.copy(chat_id=partner_id)
            logger.info(f"Message from {user_id} forwarded to {partner_id}.")
        except Exception as e:
            logger.error(f"Error forwarding message from {user_id} to {partner_id}: {e}")
            await update.message.reply_text("There was an error sending your message. Your partner might have disconnected.")
            # Optionally, trigger stop_chat_command if forwarding fails
            # await stop_chat_command(update, context) # Pass update/context correctly
    else:
        logger.warning(f"User {user_id} has 'is_matching' true but no 'match_id'. Data inconsistency.")
        await update.message.reply_text("You seem to be in a broken chat state. Please use '🛑 Stop Chat' and try again.")
        # Attempt to reset state
        await update_user_field(user_id, in_search=False, is_matching=False, match_id=None, search_type=None, current_bot_state=None)


# --- Background Matching Scheduler ---
# This function will run periodically to find and connect users.
# You will add this to application.job_queue.

async def matching_scheduler_function(context: ContextTypes.DEFAULT_TYPE): # Corrected type hint for context
    logger.info("Running matching scheduler...")
    
    # Get all users who are currently in search
    users_in_search_query = users_collection.where('in_search', '==', True)
    users_in_search_docs = users_in_search_query.stream()
    
    search_queue_gender_specific = []
    search_queue_general = [] 

    async for doc in users_in_search_docs:
        user_data = doc.to_dict()
        user_id = doc.id
        
        # Skip users who might already be matched (safety check)
        if user_data.get('is_matching') or user_data.get('match_id'):
            logger.info(f"User {user_id} unexpectedly found in_search but already matched. Resetting.")
            await users_collection.document(user_id).update({'in_search': False, 'is_matching': True}) # Adjust as per your state management
            continue

        if user_data.get('search_type') == 'gender_specific':
            unlocked_at = user_data.get('gender_feature_unlocked_at')
            # Ensure timestamp is a datetime object for calculation
            if isinstance(unlocked_at, google.cloud.firestore.Timestamp):
                unlocked_at_dt = unlocked_at.astimezone(datetime.timezone.utc)
            elif isinstance(unlocked_at, datetime):
                unlocked_at_dt = unlocked_at.astimezone(datetime.timezone.utc)
            else:
                unlocked_at_dt = None
            
            # Check if the 3-hour window is still active
            if unlocked_at_dt and (datetime.now(datetime.timezone.utc) - unlocked_at_dt < timedelta(hours=3)):
                # Ensure user's own gender and looking_for_gender are set for gender-specific search
                if user_data.get('user_gender') and user_data.get('looking_for_gender'):
                    search_queue_gender_specific.append((user_id, user_data))
                else:
                    logger.warning(f"User {user_id} in gender_specific search but missing gender data. Moving to general.")
                    await users_collection.document(user_id).update({'search_type': 'general'}) # Fallback
                    search_queue_general.append((user_id, user_data))
            else:
                logger.info(f"User {user_id} gender search window expired or not set. Moving to general.")
                await users_collection.document(user_id).update({'search_type': 'general', 'gender_feature_unlocked_at': None})
                search_queue_general.append((user_id, user_data))
        else: # 'general' search or 'search_type' is None
            search_queue_general.append((user_id, user_data))

    # --- Matching Logic ---
    matched_pairs = set() # To track users who have been matched in this cycle

    # 1. Prioritize gender-specific matches
    for i in range(len(search_queue_gender_specific)):
        user1_id, user1_data = search_queue_gender_specific[i]
        if user1_id in matched_pairs: continue

        for j in range(i + 1, len(search_queue_gender_specific)):
            user2_id, user2_data = search_queue_gender_specific[j]
            if user2_id in matched_pairs: continue

            user1_gender = user1_data.get('user_gender')
            user1_looking_for = user1_data.get('looking_for_gender')
            
            user2_gender = user2_data.get('user_gender')
            user2_looking_for = user2_data.get('looking_for_gender')

            # Basic mutual gender match logic
            is_match = False
            if user1_gender and user1_looking_for and user2_gender and user2_looking_for:
                # Check if user1's preference matches user2's gender
                pref1_matches_gender2 = (user1_looking_for == user2_gender) or (user1_looking_for == 'any')
                # Check if user2's preference matches user1's gender
                pref2_matches_gender1 = (user2_looking_for == user1_gender) or (user2_looking_for == 'any')
                
                if pref1_matches_gender2 and pref2_matches_gender1:
                    is_match = True

            if is_match:
                logger.info(f"Found gender-specific match: {user1_id} and {user2_id}")
                
                # Perform the match: Update Firestore for both users
                await users_collection.document(user1_id).update({
                    'in_search': False, 'is_matching': True, 'match_id': user2_id, 'search_type': None, 'current_bot_state': None
                })
                await users_collection.document(user2_id).update({
                    'in_search': False, 'is_matching': True, 'match_id': user1_id, 'search_type': None, 'current_bot_state': None
                })
                
                # Send start messages to both users
                try:
                    await context.bot.send_message(chat_id=user1_id, text="Match found! Say hello to your new partner!")
                    await context.bot.send_message(chat_id=user2_id, text="Match found! Say hello to your new partner!")
                except Exception as e:
                    logger.error(f"Error sending match found message: {e}")

                matched_pairs.add(user1_id)
                matched_pairs.add(user2_id)


    # 2. Process general searches for remaining users
    # Include users from gender_specific queue who didn't find a match
    all_general_search_users = [(uid, udata) for uid, udata in search_queue_general if uid not in matched_pairs]
    
    # Add remaining gender-specific users who didn't find a match
    for uid, udata in search_queue_gender_specific:
        if uid not in matched_pairs:
            all_general_search_users.append((uid, udata))

    # Now, try to match remaining users in the general queue (e.g., FIFO, random)
    # This is a basic example; your actual general matching logic might be more complex.
    if len(all_general_search_users) >= 2:
        # Simple FIFO matching for general search
        for i in range(0, len(all_general_search_users) - 1, 2):
            user1_id, _ = all_general_search_users[i]
            user2_id, _ = all_general_search_users[i+1]

            if user1_id in matched_pairs or user2_id in matched_pairs: continue

            logger.info(f"Found general match: {user1_id} and {user2_id}")
            
            # Perform the match: Update Firestore for both users
            await users_collection.document(user1_id).update({
                'in_search': False, 'is_matching': True, 'match_id': user2_id, 'search_type': None, 'current_bot_state': None
            })
            await users_collection.document(user2_id).update({
                'in_search': False, 'is_matching': True, 'match_id': user1_id, 'search_type': None, 'current_bot_state': None
            })
            
            # Send start messages to both users
            try:
                await context.bot.send_message(chat_id=user1_id, text="Match found! Say hello to your new partner!")
                await context.bot.send_message(chat_id=user2_id, text="Match found! Say hello to your new partner!")
            except Exception as e:
                logger.error(f"Error sending general match found message: {e}")

            matched_pairs.add(user1_id)
            matched_pairs.add(user2_id)


# --- Main Application Setup ---

async def post_init_callback(application: Application):
    """Callback function to run after the bot has been initialized."""
    logger.info("Bot has finished initialization. Ready to receive updates.")
    # You can add any post-initialization tasks here, e.g., send a message to admin
    # await application.bot.send_message(chat_id=ADMIN_USER_ID, text="Bot started!")

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).post_init(post_init_callback).build()

    # Conversation Handler for Feedback
    feedback_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", send_feedback_start)],
        states={
            FEEDBACK_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)], # Add a general cancel
    )

    # Conversation Handler for Report Reason (post-chat feedback)
    report_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(chat_feedback_report_start, pattern=r"^chat_feedback_report_start_(\d+)$")],
        states={
            REPORT_REASON_SELECTION: [CallbackQueryHandler(handle_specific_report_reason, pattern=r"^report_reason_")],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)], # Add a general cancel
    )

    # Conversation Handler for Support
    support_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("support", start_support_chat)],
        states={
            SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_message)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)], # Add a general cancel
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.Regex("🔍 Find a Match"), find_next_match_command))
    application.add_handler(MessageHandler(filters.Regex("🛑 Stop Chat"), stop_chat_command))
    
    # New "Search by Gender" handlers
    application.add_handler(MessageHandler(filters.Regex("👫 Search by Gender"), search_by_gender_command))
    application.add_handler(CallbackQueryHandler(gender_selection_callback, pattern='^(gender_|looking_for_gender_).*'))

    # Admin command for replying to support requests
    application.add_handler(CommandHandler("reply", admin_reply))

    # Handlers for post-chat feedback
    application.add_handler(CallbackQueryHandler(handle_chat_feedback, pattern=r"^chat_feedback_(up|down)$"))
    
    # Register conversation handlers
    application.add_handler(feedback_conv_handler)
    application.add_handler(report_conv_handler)
    application.add_handler(support_conv_handler)

    # Handler for general text messages (forwards messages between matched users)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    # Add the matching scheduler job
    # This example runs every 10 seconds. Adjust the interval as needed.
    application.job_queue.run_repeating(matching_scheduler_function, interval=10, first=5) # Start after 5 seconds

    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

