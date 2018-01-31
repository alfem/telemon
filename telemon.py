#!/usr/bin/python
# -*- coding: utf8 -*-

# Telemon: Audio Monitor via Telegram
# Author: Alfonso E.M. <alfonso@el-magnifico.org>
# Requires:
#  telegram_bot https://pypi.python.org/pypi/python-telegram-bot/
#  pyaudio https://pypi.python.org/pypi/PyAudio
#  pydub https://pypi.python.org/pypi/pydub/
#  ffmpeg or avconv

import ConfigParser # configparser in Python 3
import logging
import time

from multiprocessing import Process, Pipe

from telegram import Bot, ReplyKeyboardMarkup
from telegram.error import TelegramError

from pydub import AudioSegment # for wav to ogg conversion
import pyaudio # for audio recording
from array import array
from struct import pack
import wave
from audioop import rms # for silence detection
from io import BytesIO # to avoid saving temp files to disk


CONF = ConfigParser.ConfigParser()
CONF.read("telemon.conf")

TELEGRAM_TIMEOUT=CONF.getint("TELEGRAM","timeout")
VOLUME_THRESHOLD=CONF.getint("AUDIO","volume_threshold")
CHANNELS=CONF.getint("AUDIO","channels")
RATE=CONF.getint("AUDIO","rate")
ENDING_SILENCE=CONF.getint("AUDIO","ending_silence")
DEBUG=CONF.getboolean("MAIN","debug")
CHUNK_SIZE = 2048
FORMAT = pyaudio.paInt16
FRAME_MAX_VALUE = 2 ** 15 - 1
NORMALIZE_MINUS_ONE_dB = 10 ** (-1.0 / 20)
TRIM_APPEND = RATE / 4
ENDING_SILENCE_CHUNKS=ENDING_SILENCE * RATE / CHUNK_SIZE

LOGGER = logging.getLogger()

if DEBUG:
    print "DEBUG MODE"
    logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def audiomon(conn):

  audio = pyaudio.PyAudio()
  stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, output=False, frames_per_buffer=CHUNK_SIZE)
  listening=True
  user_quit=False

  while not user_quit:
        LOGGER.debug("LISTENING")
        conn.send(["Listening..."])  
        silent_chunks = 0
        sound_started = False
        data_all = array('h')

        while not user_quit:
            if conn.poll():
                for r in conn.recv():
                    print type(r)
                    if DEBUG:
                        LOGGER.debug("Audiomon received "+r)
                    if r == 'quit':
                       user_quit = True
                       listening=False
                    elif r == 'stop':
                       listening=False
                       sound_started = False              
                       conn.send(["Not listening"])
                    elif r == 'start':
                       listening=True
                       conn.send(["Listening again"])
    
            if listening:
                try:
                    data_chunk = array('h', stream.read(CHUNK_SIZE))
                except IOError as e:
                    data = '\x00'

                silent = is_silent(data_chunk)

                if sound_started:
                    data_all.extend(data_chunk)
                    if silent:
                        silent_chunks += 1
                        if silent_chunks > ENDING_SILENCE_CHUNKS:
                            break
                    else: 
                        silent_chunks = 0
                elif not silent:
                    LOGGER.debug("SOUND DETECTED!") 
                    conn.send(["Sound detected"])
                    sound_started = True              

        if user_quit:
            LOGGER.debug("audiomon exiting") 
            stream.stop_stream()
            stream.close()
            audio.terminate()
            break

        LOGGER.debug("SILENCE") 

        data = pack('<' + ('h' * len(data_all)), *data_all)

        output = BytesIO()
        wave_file = wave.open(output, 'wb')
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(audio.get_sample_size(FORMAT))
        wave_file.setframerate(RATE)
        wave_file.writeframes(data)
        conn.send([output])
        wave_file.close()

        time.sleep(1)

  return

def is_silent(data_chunk):
    m = rms(data_chunk, 2)  #width=2 for format=paInt16
    return m < VOLUME_THRESHOLD



def save_config():
    with open('telemon.conf', 'wb') as configfile:
        CONF.write(configfile)


bot = Bot(CONF.get("TELEGRAM","token"))

bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text="Bot ready")

menu_kb = [['-sensitive', '+sensitive'], 
                  ['stop listening', 'start listening'],
                  ['alarm', 'quit']]
menu_kb_markup = ReplyKeyboardMarkup(menu_kb)

bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text="Actions", reply_markup=menu_kb_markup)

main_pipe, task_pipe = Pipe(True)
audiomon_process = Process(target=audiomon, args=(task_pipe,))
audiomon_process.daemon = True
audiomon_process.start()

update_id=0
user_quit=False


while not user_quit:
  try:
      telegram_updates=bot.get_updates(offset=update_id, timeout=TELEGRAM_TIMEOUT)
  except:
      if DEBUG:
          LOGGER.debug("Telegram Timeout getting updates")
      telegram_updates=[]
  for update in telegram_updates:
      user_command=update.message.text
      LOGGER.debug("User command received:"+str(update_id)+"-"+user_command)
      update_id = update.update_id + 1

      if user_command == "quit":
        main_pipe.send(["quit"])
        audiomon_process.join()
        user_quit=True
        telegram_updates=bot.get_updates(offset=update_id, timeout=TELEGRAM_TIMEOUT) # mark this as read or Telegram will send it again
        break

      elif user_command == "-sensitive":
        VOLUME_THRESHOLD += 100
        CONF.set("AUDIO","volume_threshold",str(VOLUME_THRESHOLD))
        save_config()
        bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text="Sensitivity:"+str(VOLUME_THRESHOLD))

      elif user_command == "+sensitive":
        VOLUME_THRESHOLD -= 100
        CONF.set("AUDIO","volume_threshold",str(VOLUME_THRESHOLD))
        save_config()
        bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text="Sensitivity:"+str(VOLUME_THRESHOLD))

      elif user_command == "stop listening":
        main_pipe.send(["stop"])

      elif user_command == "start listening":
        main_pipe.send(["start"])
      else:
        bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text="What? That is not a command!")

  if main_pipe.poll(2):
      for r in main_pipe.recv():
        print type(r)
        if isinstance(r, basestring):
          bot.send_message(chat_id=CONF.get("TELEGRAM","chat_id"), text=r) 
        else:
          audio = AudioSegment.from_wav(r).normalize(headroom=-1)
          if DEBUG:
              audio.export("telemon-debug.ogg",format="ogg")
          buffer = BytesIO()
          audio.export(buffer,format="ogg")
     
          bot.send_voice(chat_id=CONF.get("TELEGRAM","chat_id"), voice=buffer,timeout=TELEGRAM_TIMEOUT)
                   
  time.sleep(1)



