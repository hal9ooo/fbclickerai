"""Telegram bot for manual approval of member requests - saves to cache."""
import asyncio
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler,
    ContextTypes
)
import structlog
from PIL import Image
import io

from src.config import settings
from src.cache import cache

logger = structlog.get_logger()


class TelegramBot:
    """Telegram bot for remote control and manual approvals."""
    
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.admin_id = settings.telegram_admin_id
        self.app: Optional[Application] = None
        
        # Store request names by message ID for callback handling
        self._message_to_name: Dict[str, str] = {}
        
        # Bot status
        self._is_paused = False
        self._running = False
    
    @property
    def is_paused(self) -> bool:
        """Check if bot is paused."""
        return self._is_paused
    
    async def start(self):
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot")
        
        self.app = Application.builder().token(self.token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("pause", self._cmd_pause))
        self.app.add_handler(CommandHandler("resume", self._cmd_resume))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        
        # Initialize and start polling
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        self._running = True
        logger.info("Telegram bot started")
        
        # Send startup message
        await self.send_message("🤖 FBClicker bot avviato!\n\nComandi:\n/status - Stato bot\n/pause - Pausa moderazione\n/resume - Riprendi moderazione\n/help - Aiuto")
    
    async def stop(self):
        """Stop the Telegram bot."""
        if self.app and self._running:
            logger.info("Stopping Telegram bot")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._running = False
    
    async def send_message(self, text: str):
        """Send a message to the admin."""
        if self.app:
            await self.app.bot.send_message(
                chat_id=self.admin_id,
                text=text,
                parse_mode="HTML"
            )
    
    async def send_member_request(self, name: str, extra_info: Optional[str] = None, 
                                   screenshot_path: Optional[str] = None, 
                                   preview_path: Optional[str] = None):
        """Send a member request notification with approve/decline buttons.
        
        If both card and preview images are available, sends them as a single media group.
        Then sends the text message with buttons.
        """
        from telegram import InputMediaPhoto
        
        logger.info("=" * 50)
        logger.info(f"TELEGRAM SEND - Name: {name}")
        logger.info(f"  screenshot_path: {screenshot_path}")
        logger.info(f"  preview_path: {preview_path}")
        logger.info(f"  extra_info: {extra_info}")
        logger.info("=" * 50)
        
        # Generate unique ID based on name
        request_id = name.strip().lower().replace(" ", "_")[:50]
        
        # Build message text
        message = f"""<b>📥 Nuova richiesta di iscrizione</b>

<b>Nome:</b> {name}"""
        
        if extra_info:
            message += f"\n<b>Info:</b> {extra_info}"
        
        # Build inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Approva", callback_data=f"approve:{request_id}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"decline:{request_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store mapping
        self._message_to_name[request_id] = name
        
        if not self.app:
            return
        
        # Prepare images
        media_group = []
        
        # Process card screenshot (with cropping)
        card_buffer = None
        if screenshot_path:
            try:
                img = Image.open(screenshot_path)
                width, height = img.size
                crop_left = 95
                crop_right = 160
                if width > crop_left + crop_right:
                    cropped = img.crop((crop_left, 0, width - crop_right, height))
                else:
                    cropped = img
                
                card_buffer = io.BytesIO()
                cropped.save(card_buffer, format='PNG')
                card_buffer.seek(0)
            except Exception as e:
                logger.error(f"Failed to process card screenshot: {e}")
        
        # Process preview
        preview_buffer = None
        if preview_path:
            try:
                with open(preview_path, 'rb') as f:
                    preview_buffer = io.BytesIO(f.read())
                preview_buffer.seek(0)
            except Exception as e:
                logger.error(f"Failed to load preview: {e}")
        
        # Send based on what we have
        try:
            if card_buffer and preview_buffer:
                # BOTH images: send as media group (album)
                logger.info(f"Sending both images as media group for {name}")
                media_group = [
                    InputMediaPhoto(media=card_buffer, caption="👤 Scheda utente"),
                    InputMediaPhoto(media=preview_buffer, caption="📄 Anteprima post")
                ]
                await self.app.bot.send_media_group(
                    chat_id=self.admin_id,
                    media=media_group
                )
                
                # Then send text with buttons
                await self.app.bot.send_message(
                    chat_id=self.admin_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                logger.info(f"Media group + text sent for {name}")
                
            elif card_buffer:
                # Only card: send as single photo with caption and buttons
                logger.info(f"Sending card photo only for {name}")
                await self.app.bot.send_photo(
                    chat_id=self.admin_id,
                    photo=card_buffer,
                    caption=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                logger.info(f"Card photo sent for {name}")
                
            else:
                # No images: just text
                await self.app.bot.send_message(
                    chat_id=self.admin_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            # Fallback to text only
            try:
                await self.app.bot.send_message(
                    chat_id=self.admin_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            except Exception as e2:
                logger.error(f"Fallback text also failed: {e2}")
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if update.effective_user.id != self.admin_id:
            await update.message.reply_text("⛔ Non autorizzato")
            return
        
        await update.message.reply_text(
            "🤖 <b>FBClicker Bot</b>\n\n"
            "Bot per la moderazione automatica del gruppo Facebook.\n\n"
            "Usa /help per vedere i comandi disponibili.",
            parse_mode="HTML"
        )
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if update.effective_user.id != self.admin_id:
            return
        
        status = "⏸️ In pausa" if self._is_paused else "▶️ Attivo"
        pending = len(cache.get_pending_decisions())
        
        await update.message.reply_text(
            f"📊 <b>Stato Bot</b>\n\n"
            f"Stato: {status}\n"
            f"Decisioni da eseguire: {pending}",
            parse_mode="HTML"
        )
    
    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        if update.effective_user.id != self.admin_id:
            return
        
        self._is_paused = True
        await update.message.reply_text("⏸️ Moderazione in pausa")
        logger.info("Bot paused by admin")
    
    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        if update.effective_user.id != self.admin_id:
            return
        
        self._is_paused = False
        await update.message.reply_text("▶️ Moderazione ripresa")
        logger.info("Bot resumed by admin")
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if update.effective_user.id != self.admin_id:
            return
        
        await update.message.reply_text(
            "📖 <b>Comandi disponibili</b>\n\n"
            "/status - Mostra stato bot\n"
            "/pause - Metti in pausa la moderazione\n"
            "/resume - Riprendi la moderazione\n"
            "/help - Mostra questo messaggio",
            parse_mode="HTML"
        )
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks - save decision to cache."""
        query = update.callback_query
        
        if query.from_user.id != self.admin_id:
            await query.answer("⛔ Non autorizzato")
            return
        
        await query.answer()
        
        data = query.data
        action, request_id = data.split(":", 1)
        
        # Get the original name
        name = self._message_to_name.get(request_id)
        if not name:
            # Try to find by cache key
            name = request_id.replace("_", " ").title()
        
        # Save decision to cache
        if cache.set_decision(name, action):
            if action == "approve":
                await query.edit_message_caption(
                    caption=f"✅ <b>{name}</b> - Approvazione in coda!\n\n<i>Verrà eseguita al prossimo controllo.</i>",
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_caption(
                    caption=f"❌ <b>{name}</b> - Rifiuto in coda!\n\n<i>Verrà eseguito al prossimo controllo.</i>",
                    parse_mode="HTML"
                )
            logger.info("Decision saved to cache", name=name, action=action)
        else:
            await query.edit_message_caption(
                caption=f"⚠️ Richiesta non trovata in cache.\n\nPotrebbe essere già stata processata.",
                parse_mode="HTML"
            )
