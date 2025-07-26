import os
import logging
import asyncio
import asyncpg
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    ApplicationBuilder
)

# --- Configuration (IMPORTANT: For production, use environment variables!) ---
# Replace with your actual Bot Token and Database URL
BOT_TOKEN = "7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
DATABASE_URL = "postgresql://secret_meet_bot_user:i3Dqcwcwyvn5zbIspVQvtlRTiqnMKLDI@dpg-d22d64h5pdvs738ri6i0-a.oregon-postgres.render.com/secret_meet_bot"


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database Pool and Initialization ---
db_pool = None

async def init_db_pool():
    global db_pool
    if not db_pool:
        try:
            db_pool = await asyncpg.create_pool(DATABASE_URL)
            logger.info("Database connection pool created successfully.")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise

async def close_db_pool():
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed.")

async def create_tables():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                state TEXT DEFAULT 'start',
                country TEXT,
                age INT,
                gender TEXT,
                pref_gender TEXT,
                referrals_count INT DEFAULT 0,
                search_by_gender_unlocked_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS active_chats (
                chat_id SERIAL PRIMARY KEY,
                user1_id BIGINT UNIQUE REFERENCES users(user_id),
                user2_id BIGINT UNIQUE REFERENCES users(user_id),
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS waiting_queue (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_feedback (
                feedback_id SERIAL PRIMARY KEY,
                chat_id INT REFERENCES active_chats(chat_id),
                giver_id BIGINT REFERENCES users(user_id),
                receiver_id BIGINT REFERENCES users(user_id),
                feedback_type TEXT, -- 'like', 'dislike'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_state ON users(state);
            CREATE INDEX IF NOT EXISTS idx_waiting_queue_joined_at ON waiting_queue(joined_at);
            CREATE INDEX IF NOT EXISTS idx_active_chats_users ON active_chats(user1_id, user2_id);
        """)
    logger.info("Database tables checked/created successfully.")

# --- Database Operations (moved inside main.py for simplicity) ---

async def get_user_from_db(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def create_or_update_user_in_db(user_id: int, username: str, first_name: str, last_name: str, **kwargs):
    async with db_pool.acquire() as conn:
        existing_user = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", user_id)

        if existing_user:
            update_fields = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
            values = list(kwargs.values())
            query = f"""
                UPDATE users
                SET {update_fields}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            """
            await conn.execute(query, user_id, *values)
            logger.info(f"User {user_id} updated with {kwargs}.")
        else:
            fields = ["user_id", "username", "first_name", "last_name"] + list(kwargs.keys())
            placeholders = ", ".join([f"${i+1}" for i in range(len(fields))])
            values = [user_id, username, first_name, last_name] + list(kwargs.values())
            query = f"""
                INSERT INTO users ({", ".join(fields)})
                VALUES ({placeholders})
            """
            await conn.execute(query, *values)
            logger.info(f"New user {user_id} created.")

async def update_user_state_in_db(user_id: int, state: str):
    await create_or_update_user_in_db(user_id, None, None, None, state=state)

async def add_user_to_queue_db(user_id: int):
    async with db_pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO waiting_queue (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", user_id)
            logger.info(f"User {user_id} added to waiting queue.")
        except Exception as e:
            logger.error(f"Error adding user {user_id} to queue: {e}")

async def remove_user_from_queue_db(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM waiting_queue WHERE user_id = $1", user_id)
        logger.info(f"User {user_id} removed from waiting queue.")

async def get_users_in_queue_db(target_pref_gender: str = 'any'):
    async with db_pool.acquire() as conn:
        if target_pref_gender != 'any':
            # Select users whose preferred gender matches the target, or 'any'
            return await conn.fetch(
                "SELECT u.* FROM waiting_queue w JOIN users u ON w.user_id = u.user_id WHERE u.state = $1 AND (u.pref_gender = $2 OR u.pref_gender = 'any') ORDER BY w.joined_at ASC",
                USER_STATE_SEARCHING, target_pref_gender
            )
        else:
            # Select all users in queue that are in searching state
            return await conn.fetch(
                "SELECT u.* FROM waiting_queue w JOIN users u ON w.user_id = u.user_id WHERE u.state = $1 ORDER BY w.joined_at ASC",
                USER_STATE_SEARCHING
            )

async def get_active_chat_partner_db(user_id: int):
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT
                CASE
                    WHEN user1_id = $1 THEN user2_id
                    WHEN user2_id = $1 THEN user1_id
                END AS partner_id,
                chat_id, user1_id, user2_id
            FROM active_chats
            WHERE (user1_id = $1 OR user2_id = $1) AND ended_at IS NULL
            """,
            user_id
        )
        return result if result else None

async def create_active_chat_db(user1_id: int, user2_id: int):
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO active_chats (user1_id, user2_id) VALUES ($1, $2)",
                user1_id, user2_id
            )
            logger.info(f"Active chat created between {user1_id} and {user2_id}.")
            await remove_user_from_queue_db(user1_id)
            await remove_user_from_queue_db(user2_id)
            return True
        except Exception as e:
            logger.error(f"Error creating active chat: {e}")
            return False

async def end_active_chat_db(user_id: int):
    async with db_pool.acquire() as conn:
        chat_info = await conn.fetchrow(
            "SELECT chat_id, user1_id, user2_id FROM active_chats WHERE (user1_id = $1 OR user2_id = $1) AND ended_at IS NULL",
            user_id
        )
        if chat_info:
            chat_id = chat_info['chat_id']
            # Determine which one is the partner
            partner_id = chat_info['user1_id'] if chat_info['user2_id'] == user_id else chat_info['user2_id']
            await conn.execute(
                "UPDATE active_chats SET ended_at = CURRENT_TIMESTAMP WHERE chat_id = $1",
                chat_id
            )
            logger.info(f"Active chat {chat_id} ended for {user_id} and {partner_id}.")
            return {"chat_id": chat_id, "partner_id": partner_id}
        return None

async def record_feedback_db(chat_id: int, giver_id: int, receiver_id: int, feedback_type: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_feedback (chat_id, giver_id, receiver_id, feedback_type) VALUES ($1, $2, $3, $4)",
            chat_id, giver_id, receiver_id, feedback_type
        )
        logger.info(f"Feedback '{feedback_type}' recorded from {giver_id} about {receiver_id} for chat {chat_id}.")

async def increment_referral_count_db(user_id: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT referrals_count FROM users WHERE user_id = $1", user_id)
        if user:
            new_count = user['referrals_count'] + 1
            await conn.execute("UPDATE users SET referrals_count = $1 WHERE user_id = $2", new_count, user_id)
            logger.info(f"User {user_id} referrals count incremented to {new_count}.")
            return new_count
        return None

async def set_search_by_gender_unlock_time_db(user_id: int, unlock_until: datetime.datetime):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET search_by_gender_unlocked_until = $1 WHERE user_id = $2", unlock_until, user_id)
        logger.info(f"User {user_id} search_by_gender unlocked until {unlock_until}.")


# --- Matching Logic (moved inside main.py for simplicity) ---

async def is_compatible(user1_data: dict, user2_data: dict, search_pref_gender: str = 'any') -> bool:
    if user1_data['user_id'] == user2_data['user_id']:
        return False
    # Ensure all required profile fields are present and not None
    required_fields = ['country', 'age', 'gender', 'pref_gender']
    if not all(k in user1_data and user1_data[k] is not None for k in required_fields):
        logger.debug(f"User1 {user1_data['user_id']} missing required fields.")
        return False
    if not all(k in user2_data and user2_data[k] is not None for k in required_fields):
        logger.debug(f"User2 {user2_data['user_id']} missing required fields.")
        return False

    # Gender preference check (bidirectional)
    # User1's preference vs User2's gender
    u1_pref = user1_data['pref_gender'].lower()
    u2_gender = user2_data['gender'].lower()
    if u1_pref != 'any' and u1_pref != u2_gender:
        logger.debug(f"User1 {user1_data['user_id']} preference ({u1_pref}) not compatible with User2 {u2_gender}.")
        return False

    # User2's preference vs User1's gender
    u2_pref = user2_data['pref_gender'].lower()
    u1_gender = user1_data['gender'].lower()
    if u2_pref != 'any' and u2_pref != u1_gender:
        logger.debug(f"User2 {user2_data['user_id']} preference ({u2_pref}) not compatible with User1 {u1_gender}.")
        return False

    # Specific 'search by gender' filter
    if search_pref_gender != 'any':
        if search_pref_gender != user2_data['gender'].lower():
            logger.debug(f"Search by gender ({search_pref_gender}) not compatible with User2's gender ({user2_data['gender']}).")
            return False

    # Country Preference: Match only if countries are the same
    if user1_data['country'].lower() != user2_data['country'].lower():
        logger.debug(f"Countries mismatch: {user1_data['country']} vs {user2_data['country']}.")
        return False

    # Age Difference: within 5 years
    age_diff = abs(user1_data['age'] - user2_data['age'])
    if age_diff > 5:
        logger.debug(f"Age difference too large: {age_diff} years.")
        return False

    logger.info(f"Users {user1_data['user_id']} and {user2_data['user_id']} are compatible.")
    return True

async def find_and_match_users(application: Application):
    logger.info("Attempting to find and match users...")
    queue_users = await get_users_in_queue_db()

    if len(queue_users) < 2:
        logger.info("Not enough users in queue for matching.")
        return

    # Use a copy to iterate, as we will remove users as they are matched
    available_users = list(queue_users)
    matched_this_cycle = []

    # Simple N*N matching
    i = 0
    while i < len(available_users):
        user1 = available_users[i]
        j = i + 1
        while j < len(available_users):
            user2 = available_users[j]

            # Ensure they are not already in an active chat
            if await get_active_chat_partner_db(user1['user_id']) or await get_active_chat_partner_db(user2['user_id']):
                j += 1
                continue

            # Check for specific search by gender preference
            user1_state = user1.get('state')
            user2_state = user2.get('state')

            # Determine the effective preferred gender for the search
            # If user1 initiated a specific gender search (state USER_STATE_SEARCHING_GENDER), use that.
            # Otherwise, use 'any' or their stored pref_gender as a general search.
            # This logic needs to be refined if 'search by gender' is a persistent state.
            # For simplicity, if 'search by gender' implies a specific target, we need to pass it.
            # For this matching loop, we'll assume a general find for now.
            # The 'search by gender' specific matching will be handled when the user explicitly triggers it.

            if await is_compatible(user1, user2):
                if await create_active_chat_db(user1['user_id'], user2['user_id']):
                    matched_this_cycle.append((user1['user_id'], user2['user_id']))
                    logger.info(f"Matched {user1['user_id']} with {user2['user_id']}")

                    # Send messages to matched users
                    await application.bot.send_message(chat_id=user1['user_id'], text="🥳 Match found! Say hello to your new chat partner!")
                    await application.bot.send_message(chat_id=user2['user_id'], text="🥳 Match found! Say hello to your new chat partner!")
                    await update_user_state_in_db(user1['user_id'], USER_STATE_IN_CHAT)
                    await update_user_state_in_db(user2['user_id'], USER_STATE_IN_CHAT)

                    # Remove matched users from the list and restart scan for next pair
                    available_users = [u for u in available_users if u['user_id'] not in {user1['user_id'], user2['user_id']}]
                    i = 0 # Reset i to rescan the updated list from beginning
                    break # Break inner loop, as user1 is matched
                else:
                    j += 1
            else:
                j += 1
        else: # If inner loop completes without a break (no match for current user1)
            i += 1

    if not matched_this_cycle:
        logger.info("No new matches found in this cycle.")


async def matching_scheduler(application: Application):
    """Schedules the matching function to run periodically."""
    while True:
        await find_and_match_users(application) # Pass application context
        await asyncio.sleep(15) # Check every 15 seconds

# --- Bot Command Handlers and States ---

# Define states for user interaction flow
USER_STATE_START = 'start'
USER_STATE_AWAIT_COUNTRY = 'await_country'
USER_STATE_AWAIT_AGE = 'await_age'
USER_STATE_AWAIT_GENDER = 'await_gender'
USER_STATE_AWAIT_PREF_GENDER = 'await_pref_gender'
USER_STATE_READY_TO_FIND = 'ready_to_find'
USER_STATE_IN_CHAT = 'in_chat'
USER_STATE_SEARCHING = 'searching'
USER_STATE_AWAIT_SEARCH_GENDER_PREF = 'await_search_gender_pref' # New state for 'Search by Gender'


# Country options for inline keyboard
COUNTRY_OPTIONS = [
    ["India", "USA", "UK"],
    ["Canada", "Australia", "Germany"],
    ["France", "Brazil", "Japan"],
    ["Other"] # Fallback for countries not listed
]

def get_country_keyboard():
    keyboard = []
    for row in COUNTRY_OPTIONS:
        keyboard.append([InlineKeyboardButton(country, callback_data=f'country_{country.lower().replace(" ", "_")}') for country in row])
    return InlineKeyboardMarkup(keyboard)

def get_gender_keyboard(prefix='gender'):
    keyboard = [
        [InlineKeyboardButton("Male", callback_data=f'{prefix}_male')],
        [InlineKeyboardButton("Female", callback_data=f'{prefix}_female')],
        [InlineKeyboardButton("Other", callback_data=f'{prefix}_other')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_pref_gender_keyboard(prefix='pref_gender'):
    keyboard = [
        [InlineKeyboardButton("Male", callback_data=f'{prefix}_male')],
        [InlineKeyboardButton("Female", callback_data=f'{prefix}_female')],
        [InlineKeyboardButton("Any", callback_data=f'{prefix}_any')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton("Find a Partner")],
        [KeyboardButton("Search by Gender")],
        [KeyboardButton("My Profile"), KeyboardButton("Help")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    await create_or_update_user_in_db(
        user.id, user.username, user.first_name, user.last_name,
        state=USER_STATE_AWAIT_COUNTRY
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"👋 Welcome {user.first_name} to The Secret Meet! Let's find you a chat partner.\n"
            "First, please select your country:"
        ),
        reply_markup=get_country_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    text = update.message.text

    user_data = await get_user_from_db(user_id)
    if not user_data:
        await context.bot.send_message(chat_id=user_id, text="Please use the /start command to begin.", reply_markup=get_main_menu_keyboard())
        return

    current_state = user_data['state']
    partner_info = await get_active_chat_partner_db(user_id) # Returns dict or None

    if partner_info:
        # User is in an active chat session, forward the message
        try:
            await context.bot.send_message(chat_id=partner_info['partner_id'], text=text)
            logger.info(f"Message from {user_id} forwarded to {partner_info['partner_id']}")
        except Exception as e:
            logger.error(f"Failed to forward message from {user_id} to {partner_info['partner_id']}: {e}")
            await context.bot.send_message(chat_id=user_id, text="❗ Sorry, I couldn't send your message. Your partner might have left the chat.")
            # Automatically end chat if forwarding fails (partner blocked bot, etc.)
            await end_chat_session(update, context, auto_end=True)
        return

    # Handle messages based on setup states or main menu button presses
    if current_state == USER_STATE_AWAIT_COUNTRY:
        # If user typed country instead of selecting, accept it.
        country = text.strip()
        await create_or_update_user_in_db(user_id, None, None, None, country=country, state=USER_STATE_AWAIT_AGE)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Got it! Now, please enter your age (e.g., 25):"
        )
    elif current_state == USER_STATE_AWAIT_AGE:
        try:
            age = int(text.strip())
            if 13 <= age <= 99: # Example age range
                await create_or_update_user_in_db(user_id, None, None, None, age=age, state=USER_STATE_AWAIT_GENDER)
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Got it! What is your gender?", reply_markup=get_gender_keyboard()
                )
            else:
                await context.bot.send_message(chat_id=user_id, text="Please enter a valid age between 13 and 99.")
        except ValueError:
            await context.bot.send_message(chat_id=user_id, text="That doesn't look like a valid age. Please enter a number.")
    elif text == "Find a Partner":
        await find_chat_command(update, context)
    elif text == "Search by Gender":
        await search_by_gender_command(update, context)
    elif text == "My Profile":
        await show_profile_command(update, context)
    elif text == "Help":
        await help_command(update, context)
    elif current_state == USER_STATE_SEARCHING:
        await context.bot.send_message(chat_id=user_id, text="You are searching for a partner. Please wait or use /stop to cancel.")
    else:
        await context.bot.send_message(chat_id=user_id, text="I'm not sure how to handle that. Please use the main menu buttons or /help for commands.", reply_markup=get_main_menu_keyboard())


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback query
    user_id = query.from_user.id
    data = query.data

    user_data = await get_user_from_db(user_id)
    if not user_data:
        await query.edit_message_text("Please use the /start command to begin.", reply_markup=get_main_menu_keyboard())
        return

    current_state = user_data['state']

    if current_state == USER_STATE_AWAIT_COUNTRY and data.startswith('country_'):
        country = data.split('_', 1)[1].replace('_', ' ') # Handle multi-word countries
        await create_or_update_user_in_db(user_id, None, None, None, country=country, state=USER_STATE_AWAIT_AGE)
        await query.edit_message_text(
            text=f"You selected {country.capitalize()}. Now, please enter your age (e.g., 25):"
        )
    elif current_state == USER_STATE_AWAIT_GENDER and data.startswith('gender_'):
        gender = data.split('_')[1]
        await create_or_update_user_in_db(user_id, None, None, None, gender=gender, state=USER_STATE_AWAIT_PREF_GENDER)
        await query.edit_message_text(
            text=f"You selected {gender.capitalize()}. Who would you like to chat with?",
            reply_markup=get_pref_gender_keyboard()
        )
    elif current_state == USER_STATE_AWAIT_PREF_GENDER and data.startswith('pref_gender_'):
        pref_gender = data.split('_')[1]
        await create_or_update_user_in_db(user_id, None, None, None, pref_gender=pref_gender, state=USER_STATE_READY_TO_FIND)
        await query.edit_message_text(
            text=f"You'd like to chat with {pref_gender.capitalize()} users.\n"
                 "Excellent! You can now use the buttons below to find a chat partner.",
            reply_markup=get_main_menu_keyboard()
        )
    elif data.startswith('feedback_'): # Handle feedback after chat ends
        chat_id = context.user_data.get('last_chat_id')
        partner_id = context.user_data.get('last_chat_partner_id')
        feedback_type = data.split('_')[1] # 'like' or 'dislike'

        if chat_id and partner_id:
            await record_feedback_db(chat_id, user_id, partner_id, feedback_type)
            await query.edit_message_text(f"Thank you for your feedback! You chose to {feedback_type} your partner.")
            # Clear stored chat info
            context.user_data.pop('last_chat_id', None)
            context.user_data.pop('last_chat_partner_id', None)
        else:
            await query.edit_message_text("No recent chat to give feedback on.")

    elif current_state == USER_STATE_AWAIT_SEARCH_GENDER_PREF and data.startswith('search_gender_'):
        selected_pref = data.split('_')[2] # e.g., 'male', 'female', 'any'
        context.user_data['temp_search_gender_pref'] = selected_pref # Store for the actual search
        await query.edit_message_text(f"Searching for {selected_pref.capitalize()} users. Please wait...")
        await update_user_state_in_db(user_id, USER_STATE_SEARCHING)
        await add_user_to_queue_db(user_id) # Add to queue with specific pref in mind for matching loop

        # Note: The matching_scheduler runs periodically and will pick this up
        # We could also trigger a specific search function here if needed.
    else:
        await query.edit_message_text("Oops! Something went wrong or an invalid option was selected. Please use the main menu or /start if stuck.", reply_markup=get_main_menu_keyboard())

async def find_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    user_data = await get_user_from_db(user_id)

    if not user_data or user_data['state'] not in [USER_STATE_READY_TO_FIND, USER_STATE_IN_CHAT, USER_STATE_SEARCHING]:
        await context.bot.send_message(chat_id=user_id, text="Please complete your profile first using /start.", reply_markup=get_main_menu_keyboard())
        return

    if await get_active_chat_partner_db(user_id):
        await context.bot.send_message(chat_id=user_id, text="You are already in a chat. Use /next to find a new one or /stop to end.", reply_markup=get_main_menu_keyboard())
        return
    if user_data['state'] == USER_STATE_SEARCHING:
        await context.bot.send_message(chat_id=user_id, text="You are already searching for a partner. Please wait or use /stop to cancel.", reply_markup=get_main_menu_keyboard())
        return

    await add_user_to_queue_db(user_id)
    await update_user_state_in_db(user_id, USER_STATE_SEARCHING)
    await context.bot.send_message(chat_id=user_id, text="Searching for a chat partner... Please wait.", reply_markup=get_main_menu_keyboard())

async def end_chat_session(update: Update, context: ContextTypes.DEFAULT_TYPE, auto_end=False) -> None:
    user_id = update.effective_chat.id
    chat_info = await end_active_chat_db(user_id) # Returns dict with chat_id and partner_id or None

    if chat_info:
        partner_id = chat_info['partner_id']
        chat_id = chat_info['chat_id']
        try:
            await context.bot.send_message(chat_id=partner_id, text="Your chat partner has left the chat.")
        except Exception as e:
            logger.warning(f"Could not notify partner {partner_id} that chat ended: {e}")

        await update_user_state_in_db(partner_id, USER_STATE_READY_TO_FIND) # Partner is now ready to find new chat
        await context.bot.send_message(chat_id=user_id, text="You have left the chat.", reply_markup=get_main_menu_keyboard())

        # Ask for feedback from the user who ended the chat
        feedback_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👍 Like", callback_data='feedback_like')],
            [InlineKeyboardButton("👎 Dislike", callback_data='feedback_dislike')]
        ])
        # Store info in user_data for callback_query handler
        context.user_data['last_chat_id'] = chat_id
        context.user_data['last_chat_partner_id'] = partner_id

        await context.bot.send_message(chat_id=user_id, text="How was your chat partner?", reply_markup=feedback_keyboard)

    elif not auto_end: # Only notify if user explicitly called /stop or /next
        await context.bot.send_message(chat_id=user_id, text="You are not currently in an active chat.", reply_markup=get_main_menu_keyboard())

    # Ensure user is removed from queue if they were searching
    await remove_user_from_queue_db(user_id)
    # Set user state back to ready to find (unless it was an auto-end and partner not found)
    if not auto_end or not chat_info: # If auto-end but no partner found, user might still be searching
         await update_user_state_in_db(user_id, USER_STATE_READY_TO_FIND)


async def next_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    user_data = await get_user_from_db(user_id)
    if not user_data or user_data['state'] not in [USER_STATE_IN_CHAT, USER_STATE_SEARCHING, USER_STATE_READY_TO_FIND]:
        await context.bot.send_message(chat_id=user_id, text="Please use /start to set up your profile first.", reply_markup=get_main_menu_keyboard())
        return

    # End current chat if any and get feedback
    await end_chat_session(update, context, auto_end=True)

    await context.bot.send_message(chat_id=user_id, text="Ending current chat. Searching for a new partner...", reply_markup=get_main_menu_keyboard())
    await add_user_to_queue_db(user_id)
    await update_user_state_in_db(user_id, USER_STATE_SEARCHING)


async def stop_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    user_data = await get_user_from_db(user_id)
    if not user_data or user_data['state'] not in [USER_STATE_IN_CHAT, USER_STATE_SEARCHING, USER_STATE_READY_TO_FIND]:
        await context.bot.send_message(chat_id=user_id, text="You are not in an active session or searching. Use /start to begin.", reply_markup=get_main_menu_keyboard())
        return

    await end_chat_session(update, context, auto_end=False) # No auto_end, user explicitly chose to stop
    await update_user_state_in_db(user_id, USER_STATE_READY_TO_FIND) # Set to ready to find for future chats


async def search_by_gender_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    user_data = await get_user_from_db(user_id)

    if not user_data or user_data['state'] not in [USER_STATE_READY_TO_FIND, USER_STATE_IN_CHAT, USER_STATE_SEARCHING]:
        await context.bot.send_message(chat_id=user_id, text="Please complete your profile first using /start.", reply_markup=get_main_menu_keyboard())
        return

    if await get_active_chat_partner_db(user_id):
        await context.bot.send_message(chat_id=user_id, text="You are already in a chat. Use /next to find a new one or /stop to end.", reply_markup=get_main_menu_keyboard())
        return

    if user_data['referrals_count'] >= 3:
        if user_data['search_by_gender_unlocked_until'] and user_data['search_by_gender_unlocked_until'] > datetime.datetime.now():
            # Feature is unlocked and active
            await update_user_state_in_db(user_id, USER_STATE_AWAIT_SEARCH_GENDER_PREF)
            await context.bot.send_message(
                chat_id=user_id,
                text="You have unlocked 'Search by Gender'! For this search, who would you like to find?",
                reply_markup=get_pref_gender_keyboard(prefix='search_gender') # Use different prefix for specific search
            )
        else:
            # Feature unlocked but expired, relock and prompt for more referrals
            await set_search_by_gender_unlock_time_db(user_id, None) # Clear unlock time
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your 'Search by Gender' access has expired. You need 3 more referrals to unlock it again for 3 hours."
            )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"The 'Search by Gender' feature requires 3 referrals to unlock it for 3 hours. You currently have {user_data['referrals_count']} referrals."
        )

async def show_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    user_data = await get_user_from_db(user_id)

    if not user_data:
        await context.bot.send_message(chat_id=user_id, text="Please use /start to set up your profile.", reply_markup=get_main_menu_keyboard())
        return

    profile_text = (
        f"👤 **Your Profile:**\n"
        f"Country: {user_data.get('country', 'Not set').capitalize()}\n"
        f"Age: {user_data.get('age', 'Not set')}\n"
        f"Gender: {user_data.get('gender', 'Not set').capitalize()}\n"
        f"Preferred Gender: {user_data.get('pref_gender', 'Not set').capitalize()}\n"
        f"Referrals: {user_data.get('referrals_count', 0)}\n"
    )
    if user_data.get('search_by_gender_unlocked_until'):
        unlock_time = user_data['search_by_gender_unlocked_until']
        if unlock_time > datetime.datetime.now():
            profile_text += f"Search by Gender unlocked until: {unlock_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            profile_text += "Search by Gender: Locked (access expired)\n"
    else:
        profile_text += "Search by Gender: Locked (needs referrals)\n"

    await context.bot.send_message(chat_id=user_id, text=profile_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "Welcome to The Secret Meet!\n\n"
            "Use the main menu buttons:\n"
            "**Find a Partner:** Start searching for a general match.\n"
            "**Search by Gender:** (Locked) Find a partner by specific gender after 3 referrals for 3 hours.\n"
            "**My Profile:** View your current profile and referral count.\n\n"
            "During a chat:\n"
            "Use **/next** to leave the current chat and find a new one.\n"
            "Use **/stop** to end your current chat and stop searching.\n"
            "You will be asked for feedback after each chat ends.\n"
        ), parse_mode='Markdown', reply_markup=get_main_menu_keyboard()
    )

async def post_init(application: Application) -> None:
    logger.info("Bot application started. Initializing database and background tasks.")
    await init_db_pool()
    await create_tables()
    application.create_task(matching_scheduler(application))

async def post_shutdown(application: Application) -> None:
    logger.info("Bot application shutting down. Closing database pool.")
    await close_db_pool()


def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # Handlers for main menu buttons
    application.add_handler(MessageHandler(filters.Regex(r"^Find a Partner$"), find_chat_command))
    application.add_handler(MessageHandler(filters.Regex(r"^Search by Gender$"), search_by_gender_command))
    application.add_handler(MessageHandler(filters.Regex(r"^My Profile$"), show_profile_command))
    application.add_handler(MessageHandler(filters.Regex(r"^Help$"), help_command))

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("find", find_chat_command))
    application.add_handler(CommandHandler("next", next_chat_command))
    application.add_handler(CommandHandler("stop", stop_chat_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", show_profile_command)) # Alias for My Profile

    # Handles text messages for profile setup or forwarding (must be last MessageHandler before filters.TEXT)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Handles inline keyboard callbacks
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # For Render, you typically use Webhooks.
    if os.getenv("WEBHOOK_URL"):
        port = int(os.getenv("PORT", "8000"))
        webhook_url = os.getenv("WEBHOOK_URL")
        logger.info(f"Running with Webhook: {webhook_url}/{BOT_TOKEN}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=BOT_TOKEN,
            webhook_url=f"{webhook_url}/{BOT_TOKEN}"
        )
    else:
        logger.info("Running with Polling (for local development).")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
