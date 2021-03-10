# Flask
from flask import Flask, request, render_template, redirect
from flask_caching import Cache

# Other
import mebots
from threading import Thread
import requests
import os
import argparse

# Bot components
from factory import Factory

CACHE_TIMEOUT = 60 * 60

app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "simple"})
bot = mebots.Bot("memebot", os.environ.get("BOT_TOKEN"))

MAX_MESSAGE_LENGTH = 1000
PREFIX = "%"

factory = Factory()


# Webhook receipt and response
@app.route("/", methods=["POST"])
def receive():
    """
    Receive callback to URL when message is sent in the group.
    """
    # Retrieve data on that single GroupMe message.
    message = request.get_json()
    group_id = message["group_id"]
    print(message)
    # Begin reply process in a new thread.
    # This way, the request won't time out if a response takes too long to generate.
    Thread(target=reply, args=(message, group_id)).start()
    return "ok", 202


def reply(message, group_id):
    send(process_message(message), group_id)


def process_message(message):
    responses = []
    if message["sender_type"] == "user":
        if message["text"].startswith(PREFIX):
            instructions = message["text"][len(PREFIX):].strip().split(None, 1)
            template = instructions.pop(0).lower()
            query = instructions[0] if len(instructions) > 0 else ""
            # If not, query appropriate module for a response
            if template == "help":
                responses.append(f"Generate a meme as follows:\n\n{PREFIX}[template name]\nFirst caption\nSecond caption\netc.\n\n")
                responses.append(factory.list_templates())
            else:
                # Make sure there are enough arguments
                responses.append(factory.response(template, query))
    return responses


def send(message, group_id):
    """
    Reply in chat.
    :param message: text of message to send. May be a tuple with further data, or a list of messages.
    :param group_id: ID of group in which to send message.
    """
    # Recurse when sending multiple messages.
    if isinstance(message, list):
        for item in message:
            send(item, group_id)
        return
    data = {
        "bot_id": bot.instance(group_id).id,
    }
    image = None
    if isinstance(message, tuple):
        message, image = message
    # TODO: this is lazy
    if message is None:
        message = ""
    if len(message) > MAX_MESSAGE_LENGTH:
        # If text is too long for one message, split it up over several
        for block in [message[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(message), MAX_MESSAGE_LENGTH)]:
            send(block, group_id)
            time.sleep(0.3)
        data["text"] = ""
    else:
        data["text"] = message
    if image is not None:
        data["picture_url"] = image
    # Prevent sending message if there's no content
    # It would be rejected anyway
    if data["text"] or data.get("picture_url"):
        response = requests.post("https://api.groupme.com/v3/bots/post", json=data)
        print("Response:")
        print(data)


# Core routing
@app.route("/")
@cache.cached(timeout=CACHE_TIMEOUT)
def home():
    return render_template("index.html")


# Module interfaces
@app.route("/memes")
@cache.cached(timeout=CACHE_TIMEOUT)
def memes():
    return render_template("memes.html",
                           memes=zip(factory.templates.keys(),
                                     [len(factory.templates[template]) - 1 for template in factory.templates]))


# Local testing
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?")
    args = parser.parse_args()
    if args.command:
        print(process_message({"text": args.command, "sender_type": "user", "group_id": None}))
    else:
        while True:
            print(process_message({"text": input("> "), "sender_type": "user", "group_id": None}))
