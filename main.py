from flask import Flask
from threading import Thread
import telebot
from telebot import types
import time

# ======================
# Flask server to keep bot alive
# ======================
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ======================
# Start Flask Server
# ======================
keep_alive()

# ======================
# Telegram Bot Setup
# ======================
bot = telebot.TeleBot("7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk")

user_data = {}
connected_users = {}
waiting_users = []

# ======================
# Country and Age Setup
# ======================

COUNTRIES = [
    "🇮🇳 India", "🇺🇸 USA", "🇬🇧 UK", "🇨🇦 Canada", "🇦🇺 Australia",
    "🇩🇪 Germany", "🇫🇷 France", "🇮🇹 Italy", "🇧🇷 Brazil", "🇯🇵 Japan",
    "🇰🇷 South Korea", "🇷🇺 Russia", "🇨🇳 China", "🇲🇽 Mexico", "🇵🇰 Pakistan",
    "🇧🇩 Bangladesh", "🇳🇵 Nepal", "🇪🇬 Egypt", "🇹🇷 Turkey", "🇸🇬 Singapore",
    "🇮🇩 Indonesia", "🇲🇾 Malaysia", "🇪🇸 Spain", "🇸🇦 Saudi Arabia", "🇦🇪 UAE",
    "🇮🇷 Iran", "🇮🇶 Iraq", "🇹🇭 Thailand", "🇻🇳 Vietnam", "🇵🇭 Philippines",
    "🇳🇬 Nigeria", "🇿🇦 South Africa", "🇰🇪 Kenya", "🇨🇴 Colombia", "🇦🇷 Argentina",
    "🌍 Other"
]

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_data[user_id] = {"step": "country"}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i in range(0, len(COUNTRIES), 3):
        markup.row(*COUNTRIES[i:i+3])
    bot.send_message(user_id, "🌍 Please select your country:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get("step") == "country")
def get_country(message):
    user_id = message.chat.id
    user_data[user_id]["country"] = message.text
    user_data[user_id]["step"] = "age"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i in range(14, 51, 5):
        row = [str(age) for age in range(i, min(i+5, 51))]
        markup.row(*row)
    bot.send_message(user_id, "🎂 How old are you?", reply_markup=markup)

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get("step") == "age")
def get_age(message):
    user_id = message.chat.id
    if message.text.isdigit() and 14 <= int(message.text) <= 50:
        user_data[user_id]["age"] = message.text
        user_data[user_id]["step"] = "done"

        # Show "Find a Partner" button
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔍 Find a Partner")
        bot.send_message(user_id, "✅ Setup complete!", reply_markup=markup)
    else:
        bot.send_message(user_id, "⚠️ Please choose a valid age between 14 and 50.")

# ======================
# Connect / Disconnect Logic
# ======================

@bot.message_handler(func=lambda message: message.text == "🔍 Find a Partner")
def handle_button_connect(message):
    connect(message)

@bot.message_handler(commands=['connect'])
def connect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        bot.send_message(user_id, "⚠️ You're already connected. Use /disconnect first.")
        return

    if waiting_users:
        partner_id = waiting_users.pop(0)
        connected_users[user_id] = partner_id
        connected_users[partner_id] = user_id

        # Typing and confirmation
        bot.send_message(user_id, "🎉 Partner found!")
        bot.send_chat_action(user_id, 'typing')
        time.sleep(1)

        bot.send_message(partner_id, "🎉 Partner found!")
        bot.send_chat_action(partner_id, 'typing')
        time.sleep(1)
    else:
        waiting_users.append(user_id)
        bot.send_message(user_id, "⏳ Waiting for a partner...")

@bot.message_handler(commands=['disconnect'])
def disconnect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        partner_id = connected_users[user_id]
        bot.send_message(partner_id, "❌ Your partner has disconnected.")
        bot.send_message(user_id, "❌ Disconnected.")
        del connected_users[partner_id]
        del connected_users[user_id]

        # Feedback prompt
        bot.send_message(partner_id, "📝 How was your chat? You can give feedback if you wish.")
    elif user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "❌ You left the queue.")
    else:
        bot.send_message(user_id, "⚠️ You're not connected to anyone.")

# ======================
# Forward Messages Between Users
# ======================

@bot.message_handler(func=lambda message: True)
def forward_messages(message):
    user_id = message.chat.id
    if user_id in connected_users:
        partner_id = connected_users[user_id]
        try:
            bot.send_chat_action(partner_id, 'typing')
            time.sleep(0.5)
            bot.send_message(partner_id, message.text)
        except:
            bot.send_message(user_id, "⚠️ Message delivery failed.")
    elif user_data.get(user_id, {}).get("step") == "done":
        bot.send_message(user_id, "ℹ️ Use the button below or type /connect to start chatting anonymously.")
