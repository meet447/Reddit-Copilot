import os
from flask import Flask, render_template, jsonify
from threading import Thread
from app import main

app = Flask(__name__)
bot_thread = None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start_bot', methods=['POST'])
def start_bot():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = Thread(target=main, daemon=True)
        bot_thread.start()
        return jsonify({"status": "success", "message": "Reddit Bot started successfully!"})
    return jsonify({"status": "error", "message": "Reddit Bot is already running."})


@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    if bot_thread is not None and bot_thread.is_alive():
        return jsonify({
            "status": "error",
            "message": "Reddit Bot is running in the background and cannot be stopped safely from the web UI yet."
        })
    return jsonify({"status": "error", "message": "Reddit Bot is not running."})


@app.route('/log')
def log():
    with open("log.txt", encoding="utf-8") as file:
        return file.read()


@app.route('/commented')
def commented_posts():
    with open("commented_posts.txt", encoding="utf-8") as file:
        return file.read()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
