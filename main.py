from flask import Flask
from threading import Thread
import time
import telebot
from telebot import types

BOT_TOKEN = BOT_TOKEN = 
"7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk"
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"
def run():
    app.run(host='0.0.0.0', port=8080)
def keep_alive():
    Thread(target=run).start()
keep_alive()
connected_users = {}
user_data = {}
referrals = {}
gender_unlock_time = {}
def country_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    countries = [
        "🇮🇳 India", "🇺🇸 USA", "🇬🇧 UK", "🇪🇸 Spain", "🇸🇦 Saudi Arabia", "🇦🇪 UAE", "🇮🇷 Iran",
        "🇮🇶 Iraq", "🇹🇭 Thailand", "🇻🇳 Vietnam", "🇵🇭 Philippines", "🇳🇬 Nigeria", "🇿🇦 South Africa",
        "🇰🇪 Kenya", "🇨🇴 Colombia", "🇦🇷 Argentina", "🇸🇬 Singapore", "🇮🇩 Indonesia", "🇲🇾 Malaysia"
    ]
    for i in range(0, len(countries), 3):
        markup.add(*countries[i:i+3])
    return markup
def age_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=5)
    for i in range(14, 51, 5):
        markup.add(*[str(x) for x in range(i, min(i + 5, 51))])
    return markup
def gender_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("♂️ Male", "♀️ Female")
    return markup
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔍 Find a Partner")
    if can_search_by_gender(user_id):
        markup.row("🎯 Search by Gender")
    else:
        markup.row("🔒 Search by Gender (Invite 3)")
    return markup
def can_search_by_gender(user_id):
    if user_id in gender_unlock_time:
        return time.time() - gender_unlock_time[user_id] <= 3600
    return False
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_data[user_id] = {}
    bot.send_message(user_id, "🌍 Select your country:", reply_markup=country_keyboard())
@bot.message_handler(func=lambda m: m.chat.id in user_data and 'country' not in user_data[m.chat.id])
def set_country(message):
    user_data[message.chat.id]['country'] = message.text
    bot.send_message(message.chat.id, "🎂 Select your age:", reply_markup=age_keyboard())
@bot.message_handler(func=lambda m: m.chat.id in user_data and 'age' not in user_data[m.chat.id])
def set_age(message):
    if message.text.isdigit() and 14 <= int(message.text) <= 50:
        user_data[message.chat.id]['age'] = int(message.text)
        bot.send_message(message.chat.id, "👤 Select your gender:", reply_markup=gender_keyboard())
    else:
        bot.send_message(message.chat.id, "❗ Age must be between 14 and 50.")
@bot.message_handler(func=lambda m: m.chat.id in user_data and 'gender' not in user_data[m.chat.id])
def set_gender(message):
    if message.text in ["♂️ Male", "♀️ Female"]:
        user_data[message.chat.id]['gender'] = message.text
        bot.send_message(message.chat.id, "✅ Setup complete! Use the buttons below to start chatting.",
                         reply_markup=main_menu(message.chat.id))
    else:
        bot.send_message(message.chat.id, "❗ Please select Male or Female.")
@bot.message_handler(commands=['profile'])
def profile(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    if data:
        profile_text = f"🌍 Country: {data.get('country')}\n🎂 Age: {data.get('age')}\n👤 Gender: {data.get('gender')}"
        bot.send_message(user_id, profile_text + "\n\nWant to edit? Send /start again.")
    else:
        bot.send_message(user_id, "❗ Please complete your profile using /start.")
@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, """
🤖 *SecretMeet Bot Commands*
/connect – Find a random partner
/disconnect – Leave the chat
/profile – View your info
/help – Show this message
🎯 Search by Gender is unlocked for 1 hour after inviting 3 users.
""", parse_mode='Markdown')
@bot.message_handler(commands=['connect'])
def connect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        bot.send_message(user_id, "⚠️ You're already connected. Use /disconnect first.")
        return
    for other_id in connected_users:
        if connected_users[other_id] is None and other_id != user_id:
            connected_users[other_id] = user_id
            connected_users[user_id] = other_id
            bot.send_message(user_id, "🎉 Partner found! Say hi 👋")
            bot.send_chat_action(user_id, 'typing')
            bot.send_chat_action(other_id, 'typing')
            bot.send_message(other_id, "🎉 Partner found! Say hi 👋")
            return
    connected_users[user_id] = None
    bot.send_message(user_id, "⏳ Waiting for someone to connect...")
@bot.message_handler(commands=['disconnect'])
def disconnect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        partner = connected_users[user_id]
        if partner:
            bot.send_message(partner, "❗Your partner has left the chat.")
            connected_users[partner] = None
        del connected_users[user_id]
        bot.send_message(user_id, "❌ You have left the chat.")
    else:
        bot.send_message(user_id, "⚠️ You're not in a chat.")
@bot.message_handler(func=lambda m: True)
def chat(message):
    user_id = message.chat.id
    if user_id in connected_users and connected_users[user_id]:
        partner = connected_users[user_id]
        bot.send_chat_action(partner, 'typing')
        bot.send_message(partner, message.text)
    elif user_id in connected_users:
        bot.send_message(user_id, "⏳ Still waiting for a partner...")
    elif message.text == "🔍 Find a Partner":
        connect(message)
    elif message.text.startswith("🎯"):
        if can_search_by_gender(user_id):
            bot.send_message(user_id, "🎯 Gender search coming soon...")
        else:
            bot.send_message(user_id, "🔒 Feature locked. Invite 3 users to unlock.")
    else:
        bot.send_message(user_id, "ℹ️ Use /connect to start chatting.")
bot.infinity_polling()