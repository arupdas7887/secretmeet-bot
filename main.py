import asyncio
import logging
import os
import uuid
from datetime import datetime

import asyncpg
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Configuration
# For Render deployment, these should ideally be set as environment variables.
# But for simplicity, we're keeping them hardcoded as per previous instructions.
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"  # REPLACE WITH YOUR ACTUAL BOT TOKEN
DATABASE_URL = "postgresql://secret_meet_bot_user:i3Dqcwcwyvn5zbIspVQvtlRTiqnMKLDI@dpg-d22d64h5pdvs738ri6i0-a.oregon-postgres.render.com/secret_meet_bot" # REPLACE WITH YOUR ACTUAL DATABASE URL

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECT_COUNTRY, ENTER_AGE, SELECT_GENDER = range(3)
# Note: SELECT_PARTNER_GENDER state is REMOVED as requested.

# Database connection pool
db_pool = None

async def init_db():
    """Initializes the database connection pool and creates tables if they don't exist."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        logger.info("Database connection pool created successfully.")

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                country TEXT,
                age INT,
                gender TEXT,
                preferred_gender TEXT, -- Still keep column for existing data/future expansion
                in_search BOOLEAN DEFAULT FALSE,
                match_id UUID,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- NEW ADDITION START ---
        # Add column if it doesn't exist (for existing tables that might not have it)
        await conn.execute(
            """
            DO $$ BEGIN
                ALTER TABLE users ADD COLUMN IF NOT EXISTS in_search BOOLEAN DEFAULT FALSE;
            END $$;
            """
        )
        # --- NEW ADDITION END ---
        # Add index to `in_search` for faster lookups
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_in_search ON users (in_search);
            """
        )
        logger.info("Database tables checked/created successfully.")

async def close_db():
    """Closes the database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed.")

# User Database Operations
async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def create_user(user_id: int, username: str, full_name: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, username, full_name) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING",
            user_id, username, full_name
        )
        logger.info(f"User {user_id} created or already exists.")

async def update_user(user_id: int, **kwargs):
    async with db_pool.acquire() as conn:
        set_parts = [f"{key} = ${i+2}" for i, key in enumerate(kwargs.keys())]
        values = list(kwargs.values())
        query = f"UPDATE users SET {', '.join(set_parts)} WHERE user_id = $1"
        await conn.execute(query, user_id, *values)
        logger.info(f"User {user_id} updated with {kwargs}.")

async def remove_user_from_search(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET in_search = FALSE, match_id = NULL WHERE user_id = $1", user_id
        )
        logger.info(f"User {user_id} removed from search queue.")

async def set_user_in_search(user_id: int, in_search: bool = True):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET in_search = $1, last_active = NOW() WHERE user_id = $2", in_search, user_id
        )
        logger.info(f"User {user_id} in_search set to {in_search}.")

async def find_matching_users(user_id: int):
    async with db_pool.acquire() as conn:
        current_user = await get_user(user_id)
        if not current_user:
            return None

        query = """
        SELECT * FROM users
        WHERE in_search = TRUE
          AND user_id != $1
        """
        params = [user_id]

        if current_user['gender'] == 'male':
            query += " AND gender = 'female'"
        elif current_user['gender'] == 'female':
            query += " AND gender = 'male'"
        # If current_user['gender'] is 'other' or None, no additional gender filter applied.

        # Order by last_active to try to match more active users
        query += " ORDER BY last_active ASC LIMIT 1"

        potential_match = await conn.fetchrow(query, *params)
        return potential_match

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name

    await create_user(user_id, username, full_name)
    user_data = await get_user(user_id)

    # If user has already set profile, ask to search for match or restart
    if user_data and user_data['country'] and user_data['age'] and user_data['gender']:
        keyboard = [
            [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
            [InlineKeyboardButton("🔄 Restart Profile", callback_data="restart_profile")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Welcome back, {full_name}! Your profile is complete. What would you like to do?",
            reply_markup=reply_markup,
        )
        return ConversationHandler.END # End the conversation but wait for callback query

    # Otherwise, start profile setup
    keyboard = [
        [InlineKeyboardButton("India", callback_data="India"),
         InlineKeyboardButton("USA", callback_data="USA"),
         InlineKeyboardButton("UK", callback_data="UK")],
        [InlineKeyboardButton("Canada", callback_data="Canada"),
         InlineKeyboardButton("Australia", callback_data="Australia"),
         InlineKeyboardButton("Germany", callback_data="Germany")],
        [InlineKeyboardButton("France", callback_data="France"),
         InlineKeyboardButton("Brazil", callback_data="Brazil"),
         InlineKeyboardButton("Japan", callback_data="Japan")],
        [InlineKeyboardButton("Bhutan", callback_data="Bhutan"),
         InlineKeyboardButton("Indonesia", callback_data="Indonesia"),
         InlineKeyboardButton("Malaysia", callback_data="Malaysia")],
        [InlineKeyboardButton("Nepal", callback_data="Nepal"),
         InlineKeyboardButton("Sri Lanka", callback_data="Sri Lanka"),
         InlineKeyboardButton("Pakistan", callback_data="Pakistan")],
        [InlineKeyboardButton("Other", callback_data="Other")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to The Secret Meet! Let's find you a chat partner. First, please select your country:",
        reply_markup=reply_markup,
    )
    return SELECT_COUNTRY

async def process_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    country = query.data

    await update_user(user_id, country=country)
    await query.edit_message_text(f"You selected {country}. Now, please enter your age (e.g., 25):")
    return ENTER_AGE

async def invalid_country_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Please select a country from the options provided.")
    # Remain in current state, or resend options
    keyboard = [
        [InlineKeyboardButton("India", callback_data="India"),
         InlineKeyboardButton("USA", callback_data="USA"),
         InlineKeyboardButton("UK", callback_data="UK")],
        [InlineKeyboardButton("Canada", callback_data="Canada"),
         InlineKeyboardButton("Australia", callback_data="Australia"),
         InlineKeyboardButton("Germany", callback_data="Germany")],
        [InlineKeyboardButton("France", callback_data="France"),
         InlineKeyboardButton("Brazil", callback_data="Brazil"),
         InlineKeyboardButton("Japan", callback_data="Japan")],
        [InlineKeyboardButton("Bhutan", callback_data="Bhutan"),
         InlineKeyboardButton("Indonesia", callback_data="Indonesia"),
         InlineKeyboardButton("Malaysia", callback_data="Malaysia")],
        [InlineKeyboardButton("Nepal", callback_data="Nepal"),
         InlineKeyboardButton("Sri Lanka", callback_data="Sri Lanka"),
         InlineKeyboardButton("Pakistan", callback_data="Pakistan")],
        [InlineKeyboardButton("Other", callback_data="Other")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please select your country using the buttons:",
        reply_markup=reply_markup,
    )
    return SELECT_COUNTRY


async def process_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        age = int(update.message.text)
        if not (13 <= age <= 99): # Example age range
            await update.message.reply_text("Please enter a valid age between 13 and 99.")
            return ENTER_AGE
        await update_user(user_id, age=age)

        keyboard = [
            [InlineKeyboardButton("Male", callback_data="male")],
            [InlineKeyboardButton("Female", callback_data="female")],
            [InlineKeyboardButton("Other", callback_data="other")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("What is your gender?", reply_markup=reply_markup)
        return SELECT_GENDER
    except ValueError:
        await update.message.reply_text("Please enter a valid number for your age.")
        return ENTER_AGE

async def process_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    gender = query.data

    await update_user(user_id, gender=gender, in_search=True) # Set in_search directly
    await query.edit_message_text(f"You selected {gender}. Searching for a match now...")
    logger.info(f"User {user_id} selected gender {gender} and is now in search.")
    # No longer asking for preferred gender, directly go to "searching" or end.
    return ConversationHandler.END # End conversation after setting in_search

async def find_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    await set_user_in_search(user_id, True)
    await query.edit_message_text("Searching for a match now...")
    logger.info(f"User {user_id} clicked Find a Match.")
    # The matching_scheduler will pick them up

    return ConversationHandler.END

async def restart_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Reset user's profile data
    await update_user(user_id, country=None, age=None, gender=None, preferred_gender=None, in_search=False, match_id=None)
    logger.info(f"User {user_id} restarted profile.")

    # Restart the conversation from country selection
    keyboard = [
        [InlineKeyboardButton("India", callback_data="India"),
         InlineKeyboardButton("USA", callback_data="USA"),
         InlineKeyboardButton("UK", callback_data="UK")],
        [InlineKeyboardButton("Canada", callback_data="Canada"),
         InlineKeyboardButton("Australia", callback_data="Australia"),
         InlineKeyboardButton("Germany", callback_data="Germany")],
        [InlineKeyboardButton("France", callback_data="France"),
         InlineKeyboardButton("Brazil", callback_data="Brazil"),
         InlineKeyboardButton("Japan", callback_data="Japan")],
        [InlineKeyboardButton("Bhutan", callback_data="Bhutan"),
         InlineKeyboardButton("Indonesia", callback_data="Indonesia"),
         InlineKeyboardButton("Malaysia", callback_data="Malaysia")],
        [InlineKeyboardButton("Nepal", callback_data="Nepal"),
         InlineKeyboardButton("Sri Lanka", callback_data="Sri Lanka"),
         InlineKeyboardButton("Pakistan", callback_data="Pakistan")],
        [InlineKeyboardButton("Other", callback_data="Other")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Alright, let's reset your profile. Please select your country:",
        reply_markup=reply_markup,
    )
    return SELECT_COUNTRY

async def end_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        async with db_pool.acquire() as conn:
            # Clear match for both users
            await conn.execute(
                "UPDATE users SET in_search = FALSE, match_id = NULL WHERE match_id = $1", match_id
            )
        await update.message.reply_text("You have ended the chat. You are now out of the queue.")
        logger.info(f"Chat {match_id} ended by user {user_id}.")
    else:
        await update.message.reply_text("You are not currently in a chat or searching.")

    # Offer to restart or find new match
    keyboard = [
        [InlineKeyboardButton("🔍 Find a Match", callback_data="find_match")],
        [InlineKeyboardButton("🔄 Restart Profile", callback_data="restart_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "What would you like to do next?",
        reply_markup=reply_markup,
    )


async def send_match_found_message(user1_id, user2_id, context: ContextTypes.DEFAULT_TYPE):
    user1_obj = await context.bot.get_chat(user1_id)
    user2_obj = await context.bot.get_chat(user2_id)

    match_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET in_search = FALSE, match_id = $1 WHERE user_id IN ($2, $3)",
            match_id, user1_id, user2_id
        )

    match_info_msg = (
        "🎉 Match found! 🎉\n\n"
        "You've been connected with a new partner. Say hello!\n\n"
        "To end the chat, type /end"
    )

    try:
        await context.bot.send_message(chat_id=user1_id, text=match_info_msg)
        await context.bot.send_message(chat_id=user2_id, text=match_info_msg)
        logger.info(f"Match {match_id} found between {user1_id} and {user2_id}.")
    except Exception as e:
        logger.error(f"Error sending match found message: {e}")
        # Revert match status if messages failed
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET in_search = TRUE, match_id = NULL WHERE user_id IN ($1, $2)",
                user1_id, user2_id
            )

async def matching_scheduler(application: ApplicationBuilder):
    """Periodically tries to match users."""
    while True:
        await asyncio.sleep(15)  # Check every 15 seconds
        if not db_pool:
            logger.warning("Database pool not initialized in scheduler.")
            continue

        async with db_pool.acquire() as conn:
            users_in_search = await conn.fetch("SELECT user_id, gender FROM users WHERE in_search = TRUE")
        
        logger.info(f"Attempting to find and match users... {len(users_in_search)} users in queue.")

        if len(users_in_search) < 2:
            logger.info("Not enough users in queue for matching.")
            continue

        matched_pair = None
        for i in range(len(users_in_search)):
            user1 = users_in_search[i]
            for j in range(i + 1, len(users_in_search)):
                user2 = users_in_search[j]

                # Ensure users are not already matched or self-matching
                if user1['user_id'] == user2['user_id']:
                    continue

                # Basic opposite gender matching logic
                if (user1['gender'] == 'male' and user2['gender'] == 'female') or \
                   (user1['gender'] == 'female' and user2['gender'] == 'male') or \
                   (user1['gender'] == 'other' or user2['gender'] == 'other'): # 'Other' can match with anyone
                    matched_pair = (user1['user_id'], user2['user_id'])
                    break
            if matched_pair:
                break

        if matched_pair:
            user1_id, user2_id = matched_pair
            await send_match_found_message(user1_id, user2_id, application.bot)
        else:
            logger.info("No suitable matches found in the current queue based on gender preferences.")


async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data and user_data['match_id']:
        match_id = user_data['match_id']
        async with db_pool.acquire() as conn:
            matched_users = await conn.fetch(
                "SELECT user_id FROM users WHERE match_id = $1 AND user_id != $2",
                match_id, user_id
            )
        
        if matched_users:
            partner_id = matched_users[0]['user_id']
            try:
                # Forward all types of messages (text, photo, video, etc.)
                await context.bot.forward_message(
                    chat_id=partner_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                logger.info(f"Message from {user_id} forwarded to {partner_id}.")
            except Exception as e:
                logger.error(f"Error forwarding message from {user_id} to {partner_id}: {e}")
                await update.message.reply_text("Could not send your message to your partner. They might have left or blocked the bot.")
                # Automatically end chat if forwarding fails consistently (optional, for robustness)
                await end_match(update, context)
        else:
            await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")
            await remove_user_from_search(user_id) # Ensure user is out of search if match_id is set but partner not found
    else:
        await update.message.reply_text("You are not currently in a chat. Send /start to find a partner.")


def main() -> None:
    """Start the bot."""
    webhook_url = os.getenv("WEBHOOK_URL")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- Directly initialize DB and start scheduler here ---
    # These operations are usually done in post_init, but due to env issues,
    # we're running them directly within the main function before starting the bot loop.
    async def startup_tasks():
        await init_db()
        application.create_task(matching_scheduler(application))

    # Run the startup tasks immediately
    asyncio.run(startup_tasks())
    # --- End of direct initialization ---

    # Handlers for conversation states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_COUNTRY: [
                CallbackQueryHandler(process_country, pattern='^(India|USA|UK|Canada|Australia|Germany|France|Brazil|Japan|Bhutan|Indonesia|Malaysia|Nepal|Sri Lanka|Pakistan|Other)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, invalid_country_input),
            ],
            ENTER_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_age),
            ],
            SELECT_GENDER: [
                CallbackQueryHandler(process_gender, pattern='^(male|female|other)$'),
            ],
            # SELECT_PARTNER_GENDER state and its handlers are removed
        },
        fallbacks=[CommandHandler("start", start)], # If user gets stuck, can restart
        allow_reentry=True, # Allows users to re-enter conversation handler
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("end", end_match))
    application.add_handler(CallbackQueryHandler(find_match_callback, pattern='^find_match$'))
    application.add_handler(CallbackQueryHandler(restart_profile_callback, pattern='^restart_profile$'))

    # Handle all other messages for forwarding (corrected filter here)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))

    # The post_init and post_shutdown callbacks are removed from here.
    # The startup tasks are now run directly.
    # The database connection close will happen when the process exits.

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
