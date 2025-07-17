5import telebot from telebot import types from flask import Flask import threading import time

TOKEN = '7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk' bot = telebot.TeleBot(TOKEN) app = Flask(name)

users = {} chats = {} searching = set() referrals = {} gender_unlock_time = {}

countries = [ 'India', 'USA', 'UK', 'Canada', 'Australia', 'Germany', 'France', 'Italy', 'Spain', 'Saudi Arabia', 'UAE', 'Iran', 'Iraq', 'Thailand', 'Vietnam', 'Philippines', 'Nigeria', 'South Africa', 'Kenya', 'Colombia', 'Argentina' ]

def main_keyboard(user_id): markup = types.ReplyKeyboardMarkup(resize_keyboard=True) markup.row('🔍 Find a Partner') if referrals.get(user_id, 0) >= 5 and time.time() < gender_unlock_time.get(user_id, 0): markup.row('🎯 Search by Gender') return markup

def start_setup(message): chat_id = message.chat.id users[chat_id] = {} country_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True) for i in range(0, len(countries), 2): row = countries[i:i+2] country_markup.row(*row) bot.send_message(chat_id, "Select your country:", reply_markup=country_markup)

@bot.message_handler(commands=['start']) def start_command(message): start_setup(message)

@bot.message_handler(func=lambda m: 'country' not in users.get(m.chat.id, {})) def set_country(message): users[message.chat.id]['country'] = message.text age_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True) age_markup.row('14-17', '18-24') age_markup.row('25-35', '36-50') bot.send_message(message.chat.id, "Select your age group:", reply_markup=age_markup)

@bot.message_handler(func=lambda m: 'age' not in users.get(m.chat.id, {})) def set_age(message): users[message.chat.id]['age'] = message.text gender_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True) gender_markup.row('Male', 'Female') bot.send_message(message.chat.id, "Select your gender:", reply_markup=gender_markup)

@bot.message_handler(func=lambda m: 'gender' not in users.get(m.chat.id, {})) def set_gender(message): users[message.chat.id]['gender'] = message.text bot.send_message(message.chat.id, "✅ Setup complete!", reply_markup=main_keyboard(message.chat.id))

@bot.message_handler(func=lambda m: m.text == '🔍 Find a Partner') def find_partner(message): user_id = message.chat.id if user_id in chats: bot.send_message(user_id, "❗You're already in a chat. Type /disconnect to leave it.") return for other_id in searching: if other_id != user_id: chats[user_id] = other_id chats[other_id] = user_id searching.remove(other_id) bot.send_message(user_id, "✅ Partner found! Say hi!") bot.send_message(other_id, "✅ Partner found! Say hi!") return searching.add(user_id) bot.send_message(user_id, "🔍 Searching for a partner... Please wait.")

@bot.message_handler(func=lambda m: m.text == '🎯 Search by Gender') def gender_search(message): user_id = message.chat.id if referrals.get(user_id, 0) < 5 or time.time() > gender_unlock_time.get(user_id, 0): bot.send_message(user_id, "🔒 Unlock gender search by inviting 5 friends! You'll get access for 1 hour.") return gender_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True) gender_markup.row('Male', 'Female') bot.send_message(user_id, "Choose gender you want to chat with:", reply_markup=gender_markup)

@bot.message_handler(commands=['disconnect']) def disconnect(message): user_id = message.chat.id if user_id in chats: partner_id = chats[user_id] del chats[user_id] del chats[partner_id] bot.send_message(user_id, "❗Your partner has left the chat.", reply_markup=main_keyboard(user_id)) bot.send_message(partner_id, "❗Your partner has left the chat.", reply_markup=main_keyboard(partner_id)) else: bot.send_message(user_id, "⚠️ You're not in a chat.")

@bot.message_handler(commands=['help']) def help_command(message): help_text = ( "🆘 Help Menu\n" "/start - Begin using the bot\n" "/connect - Find a partner\n" "/disconnect - Leave chat\n" "/profile - View or update your profile\n" "/referral - Get your referral link\n" "/help - View this help message\n\n" "👍 After chat ends, rate your experience\n" "💬 Use anonymous confessions and icebreakers\n" "🧠 Personality tags match you better" ) bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['referral']) def referral_command(message): ref_link = f"https://t.me/TheSecretMeet_bot?start={message.chat.id}" bot.send_message(message.chat.id, f"🔗 Invite friends using this link: {ref_link}\nInvite 5 friends to unlock gender search for 1 hour!")

@bot.message_handler(commands=['connect']) def connect_command(message): find_partner(message)

@bot.message_handler(commands=['profile']) def profile_command(message): u = users.get(message.chat.id, {}) profile = f"🌍 Country: {u.get('country', '-') }\n🎂 Age: {u.get('age', '-') }\n🚻 Gender: {u.get('gender', '-') }" bot.send_message(message.chat.id, profile)

@bot.message_handler(func=lambda m: True) def relay_messages(message): sender = message.chat.id if sender in chats: bot.send_chat_action(chats[sender], 'typing') bot.send_message(chats[sender], message.text)

Flask for Replit or web hosting

@app.route('/') def home(): return "Bot is running."

def run(): app.run(host='0.0.0.0', port=8080)

def keep_alive(): thread = threading.Thread(target=run) thread.start()

keep_alive() bot.infinity_polling()

