# bot2.py - Complete Bot with Render 24/7 Support
# Copy this entire code and paste it into bot2.py using nano

import asyncio
import logging
import sys
import sqlite3
import time
import os
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramAPIError,
    TelegramConflictError,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramServerError
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Load environment variables
load_dotenv()

# Bot Configuration - Get from environment variables for Render
BOT_TOKEN = os.getenv('BOT_TOKEN', "8654900684:AAE4QjXUsYsqfekp8nQWDXtqGkmHz8Yc_Dg")
ADMIN_ID = int(os.getenv('ADMIN_ID', 7998643430))
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', "trusteddatasellupdate")

# Validate configuration
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID is required")
if not CHANNEL_USERNAME:
    raise ValueError("CHANNEL_USERNAME is required")

# Database Setup - Use /tmp for Render (ephemeral storage)
if os.getenv('RENDER'):
    DATABASE_PATH = Path('/tmp/users.db')
else:
    DATABASE_PATH = Path('database/users.db')

DATABASE_PATH.parent.mkdir(exist_ok=True)

# Welcome Message
WELCOME_MESSAGE = """🚀💎 WELCOME TO THE DATA SELLING BOT 💎🚀

🔥 START EARNING TODAY! 🔥

💰 MINIMUM WITHDRAWAL: ₹500 💵
📤 DAILY WITHDRAWAL LIMIT: 3 TIMES 📤
📦 1 GB DATA = ₹2,000 REWARD 💎

⚡ FAST • SIMPLE • EASY TO USE ⚡

👇👇👇
CLICK THE TELEGRAM MINI APP BUTTON BELOW TO GET STARTED! 🚀"""

# ============ LOGGING SETUP ============
def setup_logger():
    logger = logging.getLogger('telegram_bot')
    logger.setLevel(logging.INFO)
    
    # Use /tmp for logs on Render
    if os.getenv('RENDER'):
        log_dir = Path('/tmp/logs')
    else:
        log_dir = Path('logs')
    
    log_dir.mkdir(exist_ok=True)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    error_file = log_dir / f'error_{datetime.now().strftime("%Y%m%d")}.log'
    error_handler = logging.FileHandler(error_file, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)
    
    all_file = log_dir / f'all_{datetime.now().strftime("%Y%m%d")}.log'
    all_handler = logging.FileHandler(all_file, encoding='utf-8')
    all_handler.setLevel(logging.DEBUG)
    all_handler.setFormatter(file_formatter)
    logger.addHandler(all_handler)
    
    return logger

logger = setup_logger()

# ============ DATABASE ============
class Database:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.bot = None
        self._lock = asyncio.Lock()
        self._connection = None
        self._cursor = None
        self._init_database()
    
    def _init_database(self):
        self._connection = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
            isolation_level=None
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA cache_size=10000")
        self._cursor = self._connection.cursor()
        self.create_tables()
    
    def create_tables(self):
        self._cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP,
                last_active TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                verified INTEGER DEFAULT 0
            )
        ''')
        
        try:
            self._cursor.execute("ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        
        self._cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)')
        self._cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_join_date ON users(join_date)')
        
        self._cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_count INTEGER DEFAULT 0,
                total_broadcasts INTEGER DEFAULT 0,
                last_broadcast TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self._cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcast_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id INTEGER,
                user_id INTEGER,
                status TEXT,
                error TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self._cursor.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_logs_user ON broadcast_logs(user_id)')
        self._connection.commit()
    
    async def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        async with self._lock:
            try:
                self._cursor.execute(query, params)
                if fetch_one:
                    result = self._cursor.fetchone()
                    self._connection.commit()
                    return result
                elif fetch_all:
                    result = self._cursor.fetchall()
                    self._connection.commit()
                    return result
                else:
                    self._connection.commit()
                    return self._cursor.rowcount
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    logger.warning("Database locked, retrying...")
                    await asyncio.sleep(0.1)
                    return await self.execute_query(query, params, fetch_one, fetch_all)
                else:
                    logger.error(f"Database error: {e}")
                    raise
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                raise
    
    async def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        try:
            result = await self.execute_query(
                '''INSERT OR IGNORE INTO users 
                   (user_id, username, first_name, last_name, join_date, last_active, verified)
                   VALUES (?, ?, ?, ?, ?, ?, 0)''',
                (user_id, username or '', first_name or '', last_name or '', 
                 datetime.now().isoformat(), datetime.now().isoformat())
            )
            return result > 0
        except Exception as e:
            logger.error(f"Error in add_user: {e}")
            return False
    
    async def set_verified(self, user_id: int):
        try:
            await self.execute_query(
                'UPDATE users SET verified = 1, last_active = ? WHERE user_id = ?',
                (datetime.now().isoformat(), user_id)
            )
        except Exception as e:
            logger.error(f"Error in set_verified: {e}")
    
    async def is_verified(self, user_id: int) -> bool:
        try:
            result = await self.execute_query(
                'SELECT verified FROM users WHERE user_id = ?',
                (user_id,),
                fetch_one=True
            )
            return result[0] == 1 if result else False
        except Exception as e:
            logger.error(f"Error in is_verified: {e}")
            return False
    
    async def update_user_activity(self, user_id: int):
        try:
            await self.execute_query(
                'UPDATE users SET last_active = ? WHERE user_id = ?',
                (datetime.now().isoformat(), user_id)
            )
        except Exception as e:
            logger.error(f"Error in update_user_activity: {e}")
    
    async def get_user_count(self) -> int:
        try:
            result = await self.execute_query(
                'SELECT COUNT(*) FROM users WHERE is_active = 1',
                fetch_one=True
            )
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error in get_user_count: {e}")
            return 0
    
    async def get_today_users(self) -> int:
        try:
            result = await self.execute_query(
                "SELECT COUNT(*) FROM users WHERE DATE(join_date) = DATE('now')",
                fetch_one=True
            )
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error in get_today_users: {e}")
            return 0
    
    async def get_all_users(self) -> List[Dict[str, Any]]:
        try:
            results = await self.execute_query(
                'SELECT * FROM users WHERE is_active = 1',
                fetch_all=True
            )
            columns = ['user_id', 'username', 'first_name', 'last_name', 'join_date', 'last_active', 'is_active', 'verified']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"Error in get_all_users: {e}")
            return []
    
    async def increment_broadcast_count(self):
        try:
            await self.execute_query(
                '''INSERT INTO stats (broadcast_count, total_broadcasts)
                   VALUES (1, 1)
                   ON CONFLICT(id) DO UPDATE SET
                   broadcast_count = broadcast_count + 1,
                   total_broadcasts = total_broadcasts + 1,
                   last_broadcast = CURRENT_TIMESTAMP'''
            )
        except Exception as e:
            logger.error(f"Error in increment_broadcast_count: {e}")
    
    async def get_broadcast_count(self) -> int:
        try:
            result = await self.execute_query(
                'SELECT total_broadcasts FROM stats ORDER BY id DESC LIMIT 1',
                fetch_one=True
            )
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error in get_broadcast_count: {e}")
            return 0
    
    async def get_database_size(self) -> str:
        try:
            size = self.db_path.stat().st_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
            return f"{size:.2f} TB"
        except:
            return "0 B"
    
    def close(self):
        if self._connection:
            self._connection.close()

db = Database()

# ============ KEYBOARDS ============
def get_verify_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌟 Join Channel 🌟", 
                    url=f"https://t.me/{CHANNEL_USERNAME}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Verify & Continue ✅", 
                    callback_data="verify"
                )
            ]
        ]
    )
    return keyboard

def get_welcome_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Trusted Data Sell Bot 🚀",
                    url="http://t.me/TrustedDataSell_bot/Data"
                )
            ]
        ]
    )
    return keyboard

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Broadcast 📢")],
            [KeyboardButton(text="👥 Total Users 👥"), KeyboardButton(text="📊 Statistics 📊")],
            [KeyboardButton(text="❌ Cancel ❌")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

# ============ MIDDLEWARES ============
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            if event.from_user.id == ADMIN_ID:
                return await handler(event, data)
            
            if isinstance(event, Message):
                if event.text and event.text.startswith('/'):
                    if event.text in ['/start', '/help', '/admin']:
                        return await handler(event, data)
            
            if await db.is_verified(event.from_user.id):
                return await handler(event, data)
            
            try:
                member = await event.bot.get_chat_member(
                    chat_id=f"@{CHANNEL_USERNAME}", 
                    user_id=event.from_user.id
                )
                if member.status in ['member', 'administrator', 'creator']:
                    await db.set_verified(event.from_user.id)
                    return await handler(event, data)
                else:
                    return await self._prompt_join(event)
            except Exception as e:
                logger.warning(f"Channel check error: {e}")
                return await self._prompt_join(event)
        except Exception as e:
            logger.error(f"Middleware error: {e}")
            return await handler(event, data)
    
    async def _prompt_join(self, event):
        message_text = "🔐 <b>Please join our channel to continue!</b>\n\n✨ Click the button below to join, then verify ✨"
        keyboard = get_verify_keyboard()
        
        if isinstance(event, Message):
            try:
                await event.answer(message_text, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error sending prompt: {e}")
        elif isinstance(event, CallbackQuery):
            try:
                await event.message.answer(message_text, reply_markup=keyboard)
                await event.answer()
            except Exception as e:
                logger.error(f"Error sending prompt: {e}")

# ============ RATE LIMITER ============
class RateLimiter:
    def __init__(self, max_requests: int = 30, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    async def check(self, user_id: int) -> bool:
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        self.requests[user_id] = [t for t in self.requests[user_id] if now - t < self.time_window]
        
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        self.requests[user_id].append(now)
        return True

rate_limiter = RateLimiter()

# ============ STATES ============
class AdminStates(StatesGroup):
    admin_panel = State()
    broadcast_confirm = State()

# ============ ROUTERS ============
start_router = Router()
admin_router = Router()
broadcast_router = Router()
callback_router = Router()

# ============ START HANDLER ============
@start_router.message(Command('start'))
async def cmd_start(message: Message):
    try:
        user = message.from_user
        
        await db.add_user(
            user_id=user.id, 
            username=user.username, 
            first_name=user.first_name, 
            last_name=user.last_name
        )
        
        try:
            member = await message.bot.get_chat_member(
                chat_id=f"@{CHANNEL_USERNAME}", 
                user_id=user.id
            )
            
            if member.status in ['member', 'administrator', 'creator']:
                await db.set_verified(user.id)
                welcome_keyboard = get_welcome_keyboard()
                await message.answer(WELCOME_MESSAGE, reply_markup=welcome_keyboard)
                return
        except Exception as e:
            logger.warning(f"Channel check in start: {e}")
        
        verify_keyboard = get_verify_keyboard()
        await message.answer(
            "🔐 <b>Please join our channel to continue!</b>\n\n✨ Click the button below to join, then verify ✨",
            reply_markup=verify_keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.answer("❌ An error occurred. Please try again later.")

@start_router.message(Command('help'))
async def cmd_help(message: Message):
    help_text = """
🤖 <b>Bot Commands:</b>

/start - Start the bot
/help - Show this help message

For any issues, please contact support.
"""
    await message.answer(help_text)

# ============ ADMIN HANDLER ============
@admin_router.message(Command('admin'))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ You are not authorized to use this command.")
        return
    
    await state.set_state(AdminStates.admin_panel)
    admin_message = """
🔐 <b>Admin Panel</b>

Welcome to the admin panel. Choose an option below:

📢 Broadcast - Send messages to all users
👥 Total Users - View user statistics
📊 Statistics - View bot statistics
❌ Cancel - Exit admin panel
"""
    await message.answer(admin_message, reply_markup=get_admin_keyboard())

@admin_router.message(StateFilter(AdminStates.admin_panel))
async def admin_panel_actions(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Unauthorized access.")
        await state.clear()
        return
    
    text = message.text
    
    try:
        if text == "📢 Broadcast 📢" or text == "📢 Broadcast":
            await message.answer(
                "📢 <b>Broadcast Mode</b>\n\n"
                "Send me any message (text, photo, video, etc.) and I'll broadcast it to all users.\n"
                "You can include buttons, formatting, and media.\n\n"
                "Send /cancel to stop broadcast."
            )
            await state.set_state(AdminStates.broadcast_confirm)
        
        elif text == "👥 Total Users 👥" or text == "👥 Total Users":
            total_users = await db.get_user_count()
            today_users = await db.get_today_users()
            await message.answer(f"👥 <b>Total Users:</b> {total_users}\n🆕 <b>Today's Users:</b> {today_users}")
        
        elif text == "📊 Statistics 📊" or text == "📊 Statistics":
            total_users = await db.get_user_count()
            today_users = await db.get_today_users()
            broadcast_count = await db.get_broadcast_count()
            db_size = await db.get_database_size()
            stats_message = f"""
📊 <b>Bot Statistics</b>

👥 Total Users: {total_users}
🆕 Today's Users: {today_users}
📢 Broadcast Count: {broadcast_count}
💾 Database Size: {db_size}
"""
            await message.answer(stats_message)
        
        elif text == "❌ Cancel ❌" or text == "❌ Cancel":
            await message.answer("❌ Admin panel closed.")
            await state.clear()
        
        else:
            await message.answer("Invalid option. Please use the keyboard buttons.", reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"Error in admin panel: {e}")
        await message.answer("❌ An error occurred. Please try again.")

@admin_router.message(Command('cancel'), StateFilter(AdminStates.broadcast_confirm))
async def cancel_broadcast(message: Message, state: FSMContext):
    await message.answer("❌ Broadcast cancelled.")
    await state.clear()

# ============ BROADCAST HANDLER ============
class BroadcastManager:
    def __init__(self, bot):
        self.bot = bot
        self.success_count = 0
        self.failed_count = 0
        self.failed_users = []
        self._semaphore = asyncio.Semaphore(10)
    
    async def broadcast_message(self, message: Message) -> Dict[str, Any]:
        users = await db.get_all_users()
        total_users = len(users)
        
        if total_users == 0:
            return {'success': 0, 'failed': 0, 'total': 0, 'time_taken': 0}
        
        start_time = time.time()
        
        batch_size = 20
        for i in range(0, total_users, batch_size):
            batch = users[i:i + batch_size]
            tasks = []
            for user in batch:
                tasks.append(self._send_to_user_with_retry(message, user['user_id']))
            
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.1)
        
        end_time = time.time()
        await db.increment_broadcast_count()
        
        return {
            'success': self.success_count,
            'failed': self.failed_count,
            'total': total_users,
            'time_taken': end_time - start_time,
            'failed_users': self.failed_users[:10]
        }
    
    async def _send_to_user_with_retry(self, message: Message, user_id: int, max_retries: int = 3):
        async with self._semaphore:
            for attempt in range(max_retries):
                try:
                    await self._send_message_to_user(message, user_id)
                    self.success_count += 1
                    return
                except TelegramRetryAfter as e:
                    wait_time = e.retry_after
                    logger.warning(f"Rate limited for user {user_id}, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                except (TelegramNetworkError, TelegramServerError) as e:
                    logger.warning(f"Network error for user {user_id}, attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        self.failed_count += 1
                        self.failed_users.append({'user_id': user_id, 'error': str(e)})
                except TelegramForbiddenError:
                    logger.info(f"User {user_id} blocked the bot")
                    self.failed_count += 1
                    self.failed_users.append({'user_id': user_id, 'error': 'User blocked bot'})
                    return
                except Exception as e:
                    logger.error(f"Error sending to {user_id}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        self.failed_count += 1
                        self.failed_users.append({'user_id': user_id, 'error': str(e)})
    
    async def _send_message_to_user(self, original_message: Message, user_id: int):
        try:
            await original_message.copy_to(
                chat_id=user_id, 
                reply_markup=original_message.reply_markup
            )
        except Exception as e:
            await self._send_as_original(original_message, user_id)
    
    async def _send_as_original(self, original_message: Message, user_id: int):
        content_type = original_message.content_type
        
        try:
            if content_type == 'text':
                await self.bot.send_message(
                    user_id, 
                    original_message.text, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'photo':
                await self.bot.send_photo(
                    user_id, 
                    original_message.photo[-1].file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'video':
                await self.bot.send_video(
                    user_id, 
                    original_message.video.file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'animation':
                await self.bot.send_animation(
                    user_id, 
                    original_message.animation.file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'audio':
                await self.bot.send_audio(
                    user_id, 
                    original_message.audio.file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'voice':
                await self.bot.send_voice(
                    user_id, 
                    original_message.voice.file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'sticker':
                await self.bot.send_sticker(user_id, original_message.sticker.file_id)
            elif content_type == 'document':
                await self.bot.send_document(
                    user_id, 
                    original_message.document.file_id, 
                    caption=original_message.caption, 
                    parse_mode=original_message.parse_mode, 
                    reply_markup=original_message.reply_markup
                )
            elif content_type == 'contact':
                await self.bot.send_contact(
                    user_id, 
                    phone_number=original_message.contact.phone_number, 
                    first_name=original_message.contact.first_name, 
                    last_name=original_message.contact.last_name
                )
            elif content_type == 'location':
                await self.bot.send_location(
                    user_id, 
                    latitude=original_message.location.latitude, 
                    longitude=original_message.location.longitude
                )
            elif content_type == 'poll':
                await self.bot.send_poll(
                    user_id,
                    question=original_message.poll.question,
                    options=[opt.text for opt in original_message.poll.options],
                    is_anonymous=original_message.poll.is_anonymous,
                    type=original_message.poll.type,
                    allows_multiple_answers=original_message.poll.allows_multiple_answers,
                    correct_option_id=original_message.poll.correct_option_id,
                    explanation=original_message.poll.explanation,
                    explanation_parse_mode=original_message.parse_mode,
                    open_period=original_message.poll.open_period,
                    close_date=original_message.poll.close_date
                )
            elif content_type == 'video_note':
                await self.bot.send_video_note(user_id, original_message.video_note.file_id)
            else:
                logger.warning(f"Unsupported message type: {content_type}")
        except Exception as e:
            raise Exception(f"Failed to send message: {e}")

@broadcast_router.message(StateFilter(AdminStates.broadcast_confirm))
async def handle_broadcast_message(message: Message, state: FSMContext):
    # Check if admin clicked cancel
    if message.text and ("❌ Cancel" in message.text or "/cancel" in message.text):
        await message.answer("❌ Broadcast cancelled.")
        await state.clear()
        return
    
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Unauthorized access.")
        await state.clear()
        return
    
    if message.text and message.text.startswith('/'):
        return
    
    status_message = await message.answer("⏳ Starting broadcast...")
    
    try:
        broadcast_mgr = BroadcastManager(message.bot)
        result = await broadcast_mgr.broadcast_message(message)
        
        result_text = f"""
📢 <b>Broadcast Completed</b>

✅ Success: {result['success']}
❌ Failed: {result['failed']}
👥 Total Users: {result['total']}
⏱️ Time Taken: {result['time_taken']:.2f} seconds
"""
        
        if result['failed_users']:
            result_text += "\n<b>Failed Users:</b>\n"
            for user in result['failed_users'][:10]:
                result_text += f"• User ID: {user['user_id']} - Error: {user['error']}\n"
            if len(result['failed_users']) > 10:
                result_text += f"... and {len(result['failed_users']) - 10} more failures"
        
        await status_message.edit_text(result_text)
        
    except Exception as e:
        await status_message.edit_text(f"❌ Broadcast failed: {str(e)}")
        logger.error(f"Broadcast error: {e}")
    finally:
        await state.clear()

# ============ CALLBACK HANDLERS ============
@callback_router.callback_query(lambda c: c.data == 'verify')
async def handle_verify(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        
        if not await rate_limiter.check(user_id):
            await callback.answer("⏳ Please wait a moment before trying again.", show_alert=True)
            return
        
        await callback.answer("🔄 Checking your membership...")
        
        try:
            member = await callback.bot.get_chat_member(
                chat_id=f"@{CHANNEL_USERNAME}", 
                user_id=user_id
            )
            
            if member.status in ['member', 'administrator', 'creator']:
                await db.set_verified(user_id)
                
                try:
                    await callback.message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete message: {e}")
                
                await db.update_user_activity(user_id)
                
                welcome_keyboard = get_welcome_keyboard()
                await callback.message.answer(
                    WELCOME_MESSAGE, 
                    reply_markup=welcome_keyboard
                )
                
                await callback.answer("✅ Verification successful! Welcome!")
            else:
                await callback.answer(
                    "❌ You must join the channel first!\n\nPlease click 'Join Channel' button above.",
                    show_alert=True
                )
        
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                await callback.answer(
                    "⚠️ Channel not found. Please contact support.",
                    show_alert=True
                )
            elif "user not found" in str(e).lower():
                await callback.answer(
                    "❌ You must join the channel first!\n\nPlease click 'Join Channel' button above.",
                    show_alert=True
                )
            else:
                await callback.answer(
                    "❌ Verification failed. Please try again.",
                    show_alert=True
                )
                logger.error(f"Verification error: {e}")
        
        except TelegramRetryAfter as e:
            await callback.answer(
                f"⏳ Please wait {e.retry_after} seconds before trying again.",
                show_alert=True
            )
        
        except Exception as e:
            await callback.answer(
                "❌ An error occurred. Please try again.",
                show_alert=True
            )
            logger.error(f"Unexpected error in verification: {e}")
    
    except Exception as e:
        logger.error(f"Callback critical error: {e}")
        try:
            await callback.answer("❌ System error. Please try again.", show_alert=True)
        except:
            pass

# ============ ERROR HANDLING ============
@start_router.errors()
@admin_router.errors()
@broadcast_router.errors()
@callback_router.errors()
async def handle_errors(event, error):
    logger.error(f"Handler error: {error}")
    if isinstance(event, Message):
        try:
            await event.answer("❌ An error occurred. Please try again later.")
        except:
            pass
    elif isinstance(event, CallbackQuery):
        try:
            await event.answer("❌ An error occurred. Please try again.", show_alert=True)
        except:
            pass

# ============ MAIN FUNCTION ============
async def shutdown(dispatcher: Dispatcher, bot: Bot):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except:
        pass
    await dispatcher.storage.close()
    db.close()
    logger.info("Shutdown complete")

async def main():
    logger.info("Starting bot...")
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())
    
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(broadcast_router)
    dp.include_router(callback_router)
    
    db.bot = bot
    
    try:
        logger.info("Bot started successfully!")
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=['message', 'callback_query']
        )
    except TelegramConflictError:
        logger.error("Another bot instance is running. Shutting down.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await shutdown(dp, bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)