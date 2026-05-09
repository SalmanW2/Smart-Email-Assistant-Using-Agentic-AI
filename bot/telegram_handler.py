"""
Telegram Bot Handler - Complete Implementation
Handles all Telegram interactions with context-aware UI/UX
"""

import os
import time
import asyncio
import logging
import re
import urllib.request
from typing import Optional, Dict, List, Any
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from config import (
    BOT_TOKEN, OWNER_TELEGRAM_ID, WEBHOOK_URL, REDIRECT_URI,
    get_utc_now, UNDO_WINDOW_SECONDS, MAX_ATTACHMENT_SIZE_MB
)
from db.models import UserModel, LoginModel, BlocklistModel, UserAdminModel
from db.memory import ConversationMemory, EmailCache
from db.contacts import ContactManager
from bot.voice_handler import TTSHandler, VoiceTranscriber, AttachmentQAHandler
from bot.contact_manager import AIContactSuggestion
from gmail_client import GmailClient
from ai_engine import AI_Engine
from auth_manager import auth_manager_instance

logger = logging.getLogger(__name__)


# ===== BOT STATE MANAGEMENT =====
class BotState:
    """Manages bot state for individual users."""
    
    def __init__(self):
        self.user_states: Dict[str, Dict[str, Any]] = {}
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        self.undo_timers: Dict[str, asyncio.Task] = {}
    
    def get_state(self, user_id: str) -> Dict[str, Any]:
        """Gets user state."""
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                'mode': 'idle',
                'compose_data': {},
                'search_query': None,
                'current_email_id': None,
                'ai_mode_enabled': True
            }
        return self.user_states[user_id]
    
    def set_mode(self, user_id: str, mode: str):
        """Sets user mode."""
        self.get_state(user_id)['mode'] = mode
    
    def add_pending_action(self, user_id: str, action_type: str, data: Dict[str, Any]):
        """Adds action to undo queue."""
        self.pending_actions[user_id] = {
            'type': action_type,
            'data': data,
            'timestamp': time.time()
        }
    
    def get_pending_action(self, user_id: str) -> Optional[Dict]:
        """Gets pending action for undo."""
        return self.pending_actions.get(user_id)
    
    def clear_pending_action(self, user_id: str):
        """Clears pending action."""
        if user_id in self.pending_actions:
            del self.pending_actions[user_id]


bot_state = BotState()


# ===== TELEGRAM BOT HANDLER CLASS =====
class TelegramBotHandler:
    """Main Telegram bot handler with all event handlers."""
    
    def __init__(self):
        self.auth = auth_manager_instance
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine(self.gmail)
        self.notified_emails: set = set()
        self.startup_time = int(time.time() * 1000)
        
        # Initialize Telegram bot
        self.ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        
        logger.info("✅ Telegram Bot Handler initialized")
    
    def _register_handlers(self):
        """Registers all telegram handlers."""
        # Commands
        self.ptb_app.add_handler(CommandHandler("start", self.cmd_start))
        self.ptb_app.add_handler(CommandHandler("settings", self.cmd_settings))
        self.ptb_app.add_handler(CommandHandler("help", self.cmd_help))
        self.ptb_app.add_handler(CommandHandler("logout", self.cmd_logout))
        
        # Callbacks (buttons)
        self.ptb_app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Voice messages
        self.ptb_app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        # Attachments
        self.ptb_app.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            self.handle_attachment
        ))
        
        # Text messages (catch-all)
        self.ptb_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text
        ))
        
        # Error handler
        self.ptb_app.add_error_handler(self.error_handler)
        
        logger.info("✅ All handlers registered")
    
    # ===== HELPER METHODS =====
    
    async def check_auth(self, update: Update) -> bool:
        """Checks if user is authenticated."""
        service = self.gmail.get_service()
        if not service:
            await self._request_login(update)
            return False
        return True
    
    async def _request_login(self, update: Update):
        """Requests user to login."""
        link = self.auth.get_login_link()
        kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
        text = "⚠️ *Please login first!*\nYou need to connect your Google Account to proceed."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await update.message.reply_text(
                text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
            )
    
    def _get_main_menu_kb(self) -> InlineKeyboardMarkup:
        """Returns main menu keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Inbox", callback_data="inbox_main"),
             InlineKeyboardButton("✍️ Compose", callback_data="compose_start")],
            [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")]
        ])
    
    # ===== COMMAND HANDLERS =====
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /start command."""
        user = update.effective_user
        
        # Check if user exists
        user_status = UserModel.handle_user_start(user.id, user.username, user.first_name)
        
        if user_status == "blocked":
            await update.message.reply_text("⛔ Your access has been restricted.")
            return
        
        if user_status == "pending":
            await update.message.reply_text("⏳ Your request is pending admin approval.")
            return
        
        if not await self.check_auth(update):
            return
        
        # User is authenticated
        text = "🎛️ *Welcome back!*\nWhat would you like to do?"
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=self._get_main_menu_kb()
        )
    
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /settings command."""
        if not await self.check_auth(update):
            return
        
        user_id = str(update.effective_user.id)
        user_data = UserModel.get_user(update.effective_user.id)
        ai_mode = user_data.get("ai_mode_enabled", True) if user_data else True
        
        kb = [
            [InlineKeyboardButton(
                f"🤖 AI Mode: {'✅ ON' if ai_mode else '❌ OFF'}",
                callback_data="toggle_ai_mode"
            )],
            [InlineKeyboardButton("📋 My Contacts", callback_data="contacts_list")],
            [InlineKeyboardButton("🚪 Logout", callback_data="action_logout")],
            [InlineKeyboardButton("❌ Close", callback_data="close_menu")]
        ]
        
        text = "⚙️ *Settings*\n\nConfigure your assistant or manage your account."
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /help command."""
        text = """
🤖 *Smart Email Assistant Help*

*Main Features:*
📥 *Inbox* - View recent emails
✍️ *Compose* - Send new emails
🔍 *Search* - Find specific emails
🎙️ *Voice* - Send voice commands
📎 *Attachments* - Upload and send files

*Commands:*
/start - Show main menu
/settings - Configure assistant
/help - Show this message
/logout - Sign out

*AI Features:*
• Auto-suggest contacts
• Summarize emails
• Draft replies
• Answer attachment questions
• Voice summaries (on demand)

*Tips:*
Just type naturally! Tell the bot what you want to do.
Use /settings to toggle AI Mode on/off.
"""
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def cmd_logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /logout command."""
        user_id = update.effective_user.id
        
        if LoginModel.logout_user(user_id):
            self.gmail.service = None
            await update.message.reply_text(
                "✅ Logged out successfully.\n\nSend /start to login again.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Already logged out.")
    
    # ===== CALLBACK HANDLER (All button clicks) =====
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles all inline button callbacks."""
        query = update.callback_query
        user_id = str(update.effective_user.id)
        data = query.data
        await query.answer()
        
        if not await self.check_auth(update):
            return
        
        try:
            # ===== CONTACT SELECTION =====
            if data.startswith("select_contact_"):
                email = "_".join(data.split("_")[2:])
                state = bot_state.get_state(user_id)['compose_data']
                state['to'] = email
                state['step'] = 'await_subject'
                
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                await query.edit_message_text(
                    f"✅ *To:* {email}\n\n*Subject?*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            # ===== SEND DRAFT =====
            elif data == "send_draft":
                state = bot_state.get_state(user_id)['compose_data']
                await query.edit_message_text("⏳ *Sending email...*")
                
                result = await asyncio.to_thread(
                    self.gmail.send_email,
                    state['to'],
                    state['subject'],
                    state['body'],
                    state.get('attachments', []),
                    user_id
                )
                
                # Log & update contacts
                ConversationMemory.log_conversation(
                    update.effective_user.id,
                    f"Sent email to {state['to']}: {state['subject']}",
                    "Email sent successfully",
                    "email_send"
                )
                
                ContactManager.add_or_update_contact(
                    update.effective_user.id,
                    state['to'],
                    context_topics=['email_sent']
                )
                
                bot_state.set_mode(user_id, 'idle')
                kb = [[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]]
                
                await query.edit_message_text(
                    f"✅ {result}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            # ===== GET ATTACHMENTS =====
            elif data.startswith("getatt_"):
                m_id = data.split("_")[1]
                await query.edit_message_text("⏳ *Downloading attachments...*")
                
                file_paths = await asyncio.to_thread(self.gmail.get_attachments, m_id)
                
                if not file_paths:
                    kb = [[InlineKeyboardButton("🔙 Back", callback_data=f"read_{m_id}")]]
                    await query.edit_message_text(
                        "📭 *No attachments found.*",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                else:
                    await query.edit_message_text("📤 *Sending files...*")
                    
                    for fp in file_paths:
                        try:
                            with open(fp, 'rb') as f:
                                await context.bot.send_document(
                                    chat_id=update.effective_chat.id,
                                    document=f
                                )
                            os.remove(fp)
                        except Exception as e:
                            logger.error(f"File send error: {e}")
                    
                    await query.delete_message()
            
            # ===== MAIN MENU & NAVIGATION =====
            elif data == "inbox_main":
                await self._show_inbox(query, user_id)
            
            elif data == "compose_start":
                bot_state.set_mode(user_id, 'compose')
                bot_state.get_state(user_id)['compose_data'] = {
                    'step': 'await_to',
                    'to': '',
                    'subject': '',
                    'body': '',
                    'attachments': []
                }
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                await query.edit_message_text(
                    "✍️ *Compose Email*\n\nWho is this email for?\n_(Enter email or contact name)_",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            elif data == "search_prompt":
                bot_state.set_mode(user_id, 'search')
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                await query.edit_message_text(
                    "🔍 *Search Emails*\n\nWhat are you looking for?\n_(e.g., 'from:john', 'project', 'is:unread')_",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            elif data == "settings_menu":
                user_data = UserModel.get_user(update.effective_user.id)
                ai_mode = user_data.get("ai_mode_enabled", True) if user_data else True
                
                kb = [
                    [InlineKeyboardButton(
                        f"🤖 AI Mode: {'✅ ON' if ai_mode else '❌ OFF'}",
                        callback_data="toggle_ai_mode"
                    )],
                    [InlineKeyboardButton("📋 My Contacts", callback_data="contacts_list")],
                    [InlineKeyboardButton("🚪 Logout", callback_data="action_logout")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ]
                
                await query.edit_message_text(
                    "⚙️ *Settings*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            elif data == "toggle_ai_mode":
                user_data = UserModel.get_user(update.effective_user.id)
                current_state = user_data.get("ai_mode_enabled", True) if user_data else True
                new_state = not current_state
                
                UserModel.toggle_ai_mode(update.effective_user.id, new_state)
                bot_state.get_state(user_id)['ai_mode_enabled'] = new_state
                
                kb = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings_menu")]]
                status = "✅ *ON*" if new_state else "❌ *OFF*"
                await query.edit_message_text(
                    f"🤖 AI Mode is now {status}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            elif data == "contacts_list":
                contacts = ContactManager.get_all_contacts(update.effective_user.id)
                
                if not contacts:
                    kb = [[InlineKeyboardButton("🔙 Back", callback_data="settings_menu")]]
                    await query.edit_message_text(
                        "📋 *No contacts yet.*\nStart composing emails to build your contact list.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                    return
                
                text = "📋 *Your Contacts:*\n\n"
                for i, contact in enumerate(contacts[:10], 1):
                    alias = contact.get("contact_alias", "")
                    name = contact.get("contact_name", "")
                    email = contact.get("email_address", "")
                    freq = contact.get("frequency_of_contact", 0)
                    
                    display = f"{alias or name or email} ({freq}x)"
                    text += f"{i}. {display}\n"
                
                kb = [[InlineKeyboardButton("🔙 Back", callback_data="settings_menu")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            
            elif data == "action_logout":
                if LoginModel.logout_user(update.effective_user.id):
                    self.gmail.service = None
                    await query.edit_message_text(
                        "✅ *Logged out successfully.*\n\nSend /start to login again.",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text("❌ Logout failed.")
            
            elif data == "back_to_menu":
                await query.edit_message_text(
                    "🎛️ *Main Menu*\n\nWhat would you like to do?",
                    parse_mode="Markdown",
                    reply_markup=self._get_main_menu_kb()
                )
            
            elif data == "close_menu":
                await query.delete_message()
            
            elif data == "cancel_action":
                bot_state.set_mode(user_id, 'idle')
                await query.edit_message_text(
                    "❌ *Cancelled.*\n\nWhat else can I help with?",
                    parse_mode="Markdown",
                    reply_markup=self._get_main_menu_kb()
                )
            
            # ===== EMAIL ACTIONS =====
            elif data.startswith("read_"):
                m_id = data.split("_")[1]
                await self._show_email_detail(query, m_id, user_id)
            
            elif data.startswith("sum_"):
                m_id = data.split("_")[1]
                await query.edit_message_text("⏳ *Generating summary...*")
                
                body = self.gmail.get_full_body(m_id)
                meta = self.gmail.get_email_metadata(m_id)
                summary = await asyncio.to_thread(
                    self.ai.get_summary, body, meta['sender']
                )
                
                if summary.startswith("Error"):
                    await query.edit_message_text(f"⚠️ {summary}")
                else:
                    kb = [
                        [InlineKeyboardButton("📖 Full Email", callback_data=f"read_{m_id}")],
                        [InlineKeyboardButton("🎙️ Voice Summary", callback_data=f"voicesummary_{m_id}")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                    ]
                    await query.edit_message_text(
                        f"🤖 *Summary:*\n\n{summary}",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
            
            elif data.startswith("voicesummary_"):
                m_id = data.split("_")[1]
                await query.edit_message_text("🎙️ *Generating voice summary...*")
                
                body = self.gmail.get_full_body(m_id)
                meta = self.gmail.get_email_metadata(m_id)
                summary = await asyncio.to_thread(
                    self.ai.get_summary, body, meta['sender']
                )
                
                summary_short = summary[:1000]
                
                success, result = TTSHandler.generate_voice(
                    summary_short,
                    update.effective_user.id,
                    f"/tmp/summary_{m_id}.ogg"
                )
                
                if success:
                    with open(result, 'rb') as f:
                        await context.bot.send_voice(
                            chat_id=update.effective_chat.id,
                            voice=f,
                            caption="🎙️ Email Summary"
                        )
                    os.remove(result)
                    await query.delete_message()
                else:
                    await query.edit_message_text(f"❌ Voice generation failed: {result}")
            
            elif data.startswith("del_"):
                m_id = data.split("_")[1]
                self.gmail.delete_email(m_id)
                
                kb = [
                    [InlineKeyboardButton("↩️ Undo", callback_data=f"undodel_{m_id}")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ]
                await query.edit_message_text(
                    "🗑️ *Email deleted.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                
                # Auto-remove undo button after 4 seconds
                async def remove_undo():
                    await asyncio.sleep(UNDO_WINDOW_SECONDS)
                    try:
                        kb_new = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
                        await query.edit_reply_markup(reply_markup=InlineKeyboardMarkup(kb_new))
                    except:
                        pass
                
                asyncio.create_task(remove_undo())
            
            elif data.startswith("undodel_"):
                m_id = data.split("_")[1]
                self.gmail.untrash_email(m_id)
                await self._show_email_detail(query, m_id, user_id)
            
            elif data.startswith("reply_"):
                m_id = data.split("_")[1]
                meta = self.gmail.get_email_metadata(m_id)
                
                # Extract sender email
                sender_match = re.search(r'<(.+?)>', meta['sender'])
                sender_email = sender_match.group(1) if sender_match else meta['sender']
                
                bot_state.set_mode(user_id, 'compose')
                bot_state.get_state(user_id)['compose_data'] = {
                    'step': 'await_body',
                    'to': sender_email,
                    'subject': f"Re: {meta['subject']}",
                    'body': '',
                    'attachments': [],
                    'reply_to': m_id
                }
                
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                await query.edit_message_text(
                    f"↩️ *Replying to {sender_email}*\n\nWhat's your message?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            elif data.startswith("attachment_qa_"):
                m_id = data.split("_")[2]
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data=f"read_{m_id}")]]
                await query.edit_message_text(
                    "📎 *Ask about attachment*\n\nWhat would you like to know?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                bot_state.set_mode(user_id, 'attachment_qa')
                bot_state.get_state(user_id)['current_email_id'] = m_id
        
        except Exception as e:
            logger.error(f"Callback error: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    # ===== HELPER METHODS FOR CALLBACKS =====
    
    async def _show_inbox(self, query, user_id: str):
        """Shows inbox with recent emails."""
        try:
            service = self.gmail.get_service()
            if not service:
                await self._request_login(query.message)
                return
            
            results = service.users().messages().list(
                userId='me', q='label:INBOX', maxResults=10
            ).execute()
            messages = results.get('messages', [])
            
            if not messages:
                kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="inbox_main")]]
                await query.edit_message_text(
                    "📭 *No emails found.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                return
            
            text = "📥 *Recent Emails:*\n\n"
            kb = []
            
            for idx, msg in enumerate(messages[:5], 1):
                meta = self.gmail.get_email_metadata(msg['id'])
                sender = meta['sender'][:30].replace('<', '').replace('>', '')
                subject = meta['subject'][:40].replace('<', '').replace('>', '')
                
                text += f"*{idx}.* {sender}\n_{subject}_\n\n"
                kb.append([InlineKeyboardButton(
                    f"📖 Read #{idx}",
                    callback_data=f"read_{msg['id']}"
                )])
            
            kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Inbox error: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    async def _show_email_detail(self, query, m_id: str, user_id: str):
        """Shows full email details."""
        await query.edit_message_text("⏳ *Loading email...*")
        
        try:
            body = self.gmail.get_full_body(m_id)
            meta = self.gmail.get_email_metadata(m_id)
            
            if len(body) > 2500:
                body = body[:2500] + "\n\n[Truncated...]"
            
            safe_body = body.replace('<', '').replace('>', '')
            safe_sender = meta['sender'].replace('<', '').replace('>', '')
            safe_subject = meta['subject'].replace('<', '').replace('>', '')
            
            att_count = len(meta.get('attachments', []))
            att_text = f"\n📎 *Attachments:* {att_count} file(s)" if att_count > 0 else ""
            
            formatted = f"📧 *From:* {safe_sender}\n📝 *Subject:* {safe_subject}{att_text}\n━━━━━━━━━━━━━\n\n{safe_body}"
            
            kb = []
            if att_count > 0:
                kb.append([InlineKeyboardButton("📎 Download Attachments", callback_data=f"getatt_{m_id}")])
            kb.append([
                InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{m_id}"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{m_id}")
            ])
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                formatted,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Email detail error: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    async def _send_compose_confirmation(self, user_id: str, message_obj):
        """Shows compose confirmation draft."""
        state = bot_state.get_state(user_id)['compose_data']
        
        files_text = ""
        if state.get('attachments'):
            files_text = "\n\n📎 *Attachments:*\n"
            for att in state['attachments']:
                files_text += f"• {os.path.basename(att)}\n"
        
        draft = f"""📄 *Email Draft*

*To:* {state['to']}
*Subject:* {state['subject']}
*Body:* {state['body']}{files_text}

Ready to send?"""
        
        kb = [
            [InlineKeyboardButton("✅ Send", callback_data="send_draft"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
        ]
        
        await message_obj.edit_text(
            draft,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    
    # ===== TEXT MESSAGE HANDLER =====
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles text messages with context awareness."""
        user = update.effective_user
        user_id = str(user.id)
        text = update.message.text
        
        if not await self.check_auth(update):
            return
        
        state = bot_state.get_state(user_id)
        mode = state['mode']
        
        # Log conversation
        ConversationMemory.log_conversation(user.id, text, "[Processing...]", "text")
        UserModel.update_last_activity(user.id)
        
        try:
            # ===== COMPOSE MODE =====
            if mode == 'compose':
                compose_data = state['compose_data']
                step = compose_data['step']
                
                if step == 'await_to':
                    # Try to find contact
                    contact = AIContactSuggestion.suggest_contact_for_compose(text, user.id)
                    
                    if contact:
                        compose_data['to'] = contact['email_address']
                        compose_data['step'] = 'await_subject'
                        
                        kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                        await update.message.reply_text(
                            f"✅ *To:* {AIContactSuggestion.format_contact_display(contact)}\n\n*Subject?*",
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                    else:
                        # Try email regex
                        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                        if email_match:
                            compose_data['to'] = email_match.group()
                            compose_data['step'] = 'await_subject'
                            
                            ContactManager.add_or_update_contact(
                                user.id,
                                compose_data['to'],
                                context_topics=['email_composition']
                            )
                            
                            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                            await update.message.reply_text(
                                f"✅ *To:* {compose_data['to']}\n\n*Subject?*",
                                parse_mode="Markdown",
                                reply_markup=InlineKeyboardMarkup(kb)
                            )
                        else:
                            suggestions = ContactManager.suggest_contacts(user.id, text, limit=3)
                            if suggestions:
                                text_response = "💡 Did you mean:\n"
                                kb = []
                                for i, contact in enumerate(suggestions, 1):
                                    email = contact['email_address']
                                    display = AIContactSuggestion.format_contact_display(contact)
                                    text_response += f"{i}. {display}\n"
                                    kb.append([InlineKeyboardButton(
                                        f"Select #{i}",
                                        callback_data=f"select_contact_{email}"
                                    )])
                                kb.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")])
                                await update.message.reply_text(
                                    text_response,
                                    reply_markup=InlineKeyboardMarkup(kb)
                                )
                            else:
                                await update.message.reply_text(
                                    "❌ *Email not found.* Please enter a valid email address.",
                                    parse_mode="Markdown"
                                )
                
                elif step == 'await_subject':
                    compose_data['subject'] = text
                    compose_data['step'] = 'await_body'
                    
                    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
                    await update.message.reply_text(
                        f"📝 *Subject:* {text}\n\n*Message?*",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                
                elif step == 'await_body':
                    compose_data['body'] = text
                    compose_data['step'] = 'await_attachment'
                    
                    msg = await update.message.reply_text("⏳ *Preparing draft...*")
                    await self._send_compose_confirmation(user_id, msg)
            
            # ===== SEARCH MODE =====
            elif mode == 'search':
                query_text = text
                bot_state.set_mode(user_id, 'idle')
                
                msg = await update.message.reply_text("🔍 *Searching...*")
                
                service = self.gmail.get_service()
                results = service.users().messages().list(
                    userId='me', q=query_text, maxResults=10
                ).execute()
                messages = results.get('messages', [])
                
                if not messages:
                    await msg.edit_text("📭 *No emails found.*")
                    return
                
                text_result = f"🔍 *Results for:* `{query_text}`\n\n"
                kb = []
                
                for idx, msg_item in enumerate(messages[:5], 1):
                    meta = self.gmail.get_email_metadata(msg_item['id'])
                    sender = meta['sender'][:30].replace('<', '').replace('>', '')
                    subject = meta['subject'][:40].replace('<', '').replace('>', '')
                    
                    text_result += f"*{idx}.* {sender}\n_{subject}_\n\n"
                    kb.append([InlineKeyboardButton(
                        f"📖 Read #{idx}",
                        callback_data=f"read_{msg_item['id']}"
                    )])
                
                kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")])
                
                await msg.edit_text(
                    text_result,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            
            # ===== ATTACHMENT Q&A MODE =====
            elif mode == 'attachment_qa':
                current_email_id = state.get('current_email_id')
                if not current_email_id:
                    await update.message.reply_text("❌ No email selected.")
                    return
                
                msg = await update.message.reply_text("⏳ *Analyzing attachment...*")
                
                attachments = self.gmail.get_attachments(current_email_id)
                if not attachments:
                    await msg.edit_text("📭 *No attachments found.*")
                    return
                
                file_path = attachments[0]
                answer = AttachmentQAHandler.analyze_attachment(file_path, text)
                
                os.remove(file_path)
                
                kb = [[InlineKeyboardButton("🔙 Back", callback_data=f"read_{current_email_id}")]]
                await msg.edit_text(
                    f"📎 *Answer:*\n\n{answer}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                
                bot_state.set_mode(user_id, 'idle')
            
            # ===== AI CONVERSATION MODE =====
            else:
                user_data = UserModel.get_user(user.id)
                if not (user_data and user_data.get("ai_mode_enabled", True)):
                    await update.message.reply_text(
                        "🤖 *AI Mode is disabled.* Enable it in /settings.",
                        parse_mode="Markdown"
                    )
                    return
                
                context_text = ConversationMemory.get_recent_context(user.id, days=1)
                topic = ConversationMemory.get_current_topic(user.id) or "General"
                
                ContactManager.auto_extract_emails(user.id, text, topic)
                
                msg = await update.message.reply_text("⏳ *Processing...*")
                
                full_prompt = f"{context_text}\n\nUser: {text}"
                response = await asyncio.to_thread(
                    self.ai.agent_chat, full_prompt, str(user.id)
                )
                
                ConversationMemory.log_conversation(
                    user.id,
                    text,
                    response,
                    "ai_response",
                    current_topic=topic
                )
                
                if ConversationMemory.should_generate_summary(user.id):
                    pass  # Summary generation in next phase
                
                kb = [[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]]
                await msg.edit_text(
                    response,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        
        except Exception as e:
            logger.error(f"Text handler error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    # ===== VOICE MESSAGE HANDLER =====
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles voice messages."""
        user = update.effective_user
        user_id = str(user.id)
        
        if not await self.check_auth(update):
            return
        
        msg = await update.message.reply_text("🎙️ *Transcribing voice...*")
        
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
            
            transcribed = await asyncio.to_thread(
                VoiceTranscriber.transcribe_audio, file_path
            )
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
            if "[Audio Unclear]" in transcribed:
                await msg.edit_text("⚠️ *Audio was unclear.* Please try again.")
                return
            
            await msg.edit_text(f"🗣️ *You said:*\n_{transcribed}_\n\n⏳ Processing...")
            
            user_data = UserModel.get_user(user.id)
            if not (user_data and user_data.get("ai_mode_enabled", True)):
                await msg.edit_text(
                    f"🗣️ *Transcribed:*\n_{transcribed}_\n\n🤖 AI Mode is disabled.",
                    parse_mode="Markdown"
                )
                return
            
            context_text = ConversationMemory.get_recent_context(user.id, days=1)
            topic = ConversationMemory.get_current_topic(user.id) or "Voice Command"
            
            ContactManager.auto_extract_emails(user.id, transcribed, topic)
            
            full_prompt = f"{context_text}\n\nUser (voice): {transcribed}"
            response = await asyncio.to_thread(
                self.ai.agent_chat, full_prompt, str(user.id)
            )
            
            ConversationMemory.log_conversation(
                user.id,
                f"[VOICE] {transcribed}",
                response,
                "voice",
                current_topic=topic
            )
            
            kb = [[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]]
            await msg.edit_text(
                response,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Voice handler error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")
    
    # ===== ATTACHMENT HANDLER =====
    
    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles file attachments."""
        user = update.effective_user
        user_id = str(user.id)
        
        if not await self.check_auth(update):
            return
        
        attachment = (
            update.message.document or
            (update.message.photo[-1] if update.message.photo else None) or
            update.message.audio or
            update.message.video
        )
        
        if not attachment:
            return
        
        if attachment.file_size > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
            await update.message.reply_text(
                f"❌ *File too large.* Max {MAX_ATTACHMENT_SIZE_MB}MB allowed.",
                parse_mode="Markdown"
            )
            return
        
        msg = await update.message.reply_text("⏳ *Downloading attachment...*")
        
        try:
            file = await context.bot.get_file(attachment.file_id)
            file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
            file_path = f"/tmp/{file_name}"
            await file.download_to_drive(file_path)
            
            state = bot_state.get_state(user_id)
            mode = state['mode']
            
            if mode == 'compose':
                compose_data = state['compose_data']
                compose_data['attachments'].append(file_path)
                
                await self._send_compose_confirmation(user_id, msg)
            else:
                await msg.edit_text(
                    f"✅ *File saved:* {file_name}\n\nUse this in your next email composition.",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Attachment error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")
    
    # ===== ERROR HANDLER =====
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles errors gracefully."""
        logger.error(f"Error: {context.error}")
        if update:
            try:
                if update.message:
                    await update.message.reply_text("❌ An error occurred. Please try again.")
                elif update.callback_query:
                    await update.callback_query.edit_message_text("❌ An error occurred. Please try again.")
            except:
                pass
    
    # ===== BACKGROUND JOBS =====
    
    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        """Checks for new emails periodically."""
        try:
            service = self.gmail.get_service()
            if not service:
                return
            
            results = service.users().messages().list(
                userId='me', q='is:unread', maxResults=3
            ).execute()
            messages = results.get('messages', [])
            
            for msg in messages:
                m_id = msg['id']
                if m_id not in self.notified_emails:
                    self.notified_emails.add(m_id)
                    
                    msg_data = service.users().messages().get(
                        userId='me', id=m_id, format='minimal'
                    ).execute()
                    internal_date = int(msg_data.get('internalDate', 0))
                    
                    if internal_date > self.startup_time:
                        meta = self.gmail.get_email_metadata(m_id)
                        
                        # Cache email
                        EmailCache.cache_email(
                            OWNER_TELEGRAM_ID,
                            m_id,
                            meta['sender'],
                            meta['sender'].split('<')[-1].rstrip('>') if '<' in meta['sender'] else meta['sender'],
                            meta['subject'],
                            self.gmail.get_full_body(m_id)
                        )
                        
                        await self._notify_new_email(context, meta, m_id)
        except Exception as e:
            logger.error(f"Email check error: {e}")
    
    async def _notify_new_email(self, context: ContextTypes.DEFAULT_TYPE, meta: dict, m_id: str):
        """Notifies user of new email."""
        text = f"🔔 *New Email!*\n👤 {meta['sender']}\n📝 {meta['subject']}"
        kb = [
            [InlineKeyboardButton("📖 Read", callback_data=f"read_{m_id}"),
             InlineKeyboardButton("📋 Summary", callback_data=f"sum_{m_id}")]
        ]
        
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    
    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        """Keeps server awake."""
        try:
            await asyncio.to_thread(urllib.request.urlopen, WEBHOOK_URL)
            logger.info("✅ Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Ping failed: {e}")


# Initialize bot handler
bot_handler = TelegramBotHandler()