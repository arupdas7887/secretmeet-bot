from flask import Flask
from threading import Thread
import telebot

app = Flask('')

@app.route('/')
def home():
    return "✅ SecretMeet Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run).start()

keep_alive()

bot = telebot.TeleBot('7673817380:AAH8NkM1A3kJzB9HVdWBlrkTIaMBeol6Nyk')

connected_users = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Welcome to SecretMeet!\nUse /connect to chat anonymously.")

@bot.message_handler(commands=['connect'])
def connect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        bot.send_message(user_id, "⚠️ Already connected.")
        return

    for other_id in connected_users:
        if connected_users[other_id] is None and other_id != user_id:
            connected_users[other_id] = user_id
            connected_users[user_id] = other_id
            bot.send_message(user_id, "✅ Connected! Say hi 👋")
            bot.send_message(other_id, "✅ Connected! Say hi 👋")
            return

    connected_users[user_id] = None
    bot.send_message(user_id, "⏳ Waiting for someone to connect...")

@bot.message_handler(commands=['disconnect'])
def disconnect(message):
    user_id = message.chat.id
    if user_id in connected_users:
        partner = connected_users[user_id]
        if partner:
            bot.send_message(partner, "⚠️ The user has disconnected.")
            connected_users[partner] = None
        del connected_users[user_id]
        bot.send_message(user_id, "❌ Disconnected.")
    else:
        bot.send_message(user_id, "⚠️ You're not connected.")

@bot.message_handler(func=lambda m: True)
def forward(message):
    user_id = message.chat.id
    if user_id in connected_users and connected_users[user_id]:
        partner = connected_users[user_id]
        bot.send_message(partner, message.text)
    elif user_id in connected_users:
        bot.send_message(user_id, "⏳ Still waiting for a partner...")
    else:
        bot.send_message(user_id, "ℹ️ Use /connect to start a chat.")

bot.infinity_polling()
