# telemon
Telegram Audio Monitor For Raspberry Pi (and others)

# Install

You will need:

* Python (tested with 2.7)
* telegram_bot https://pypi.python.org/pypi/python-telegram-bot/
* pyaudio https://pypi.python.org/pypi/PyAudio
* pydub https://pypi.python.org/pypi/pydub/
* libav-tools or ffmpeg (from your favourite repository)


# Use

First, open your Telegram app, talk to @botfather and create a new bot

Write down the bot token in telemon.conf

Talk to your new bot. Get the chat_number and write it down in telemon.conf

Finally, start telemon.py

Your new bot will send you any sound it detects. You can adjust the sensibility
using the configuration file, or right from the bot keyboard.


