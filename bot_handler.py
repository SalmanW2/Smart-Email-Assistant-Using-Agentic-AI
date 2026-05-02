import os
import time
import uvicorn
import asyncio
import re
import html
from fastapi import Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                           MessageHandler, filters, ContextTypes)
from telegram.error import RetryAfter
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID, WEBHOOK_URL
from auth_manager import auth_manager_instance, app as fastapi_app
from gmail_client import GmailClient
from ai_engine import AI_Engine
 
class BotHandler:
    def __init__(self):
        self.auth = auth_manager_instance
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine(self.gmail)
        self.notified_emails = set() 
        self.boot_time = int(time.time() * 1000)
        self.compose_states = {} # User State Machine for Manual Compose
 
        self.ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
 
    def _register_handlers(self):
        self.ptb_app.add_handler(CommandHandler("start", self.start))
        self.ptb_app.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.ptb_app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.ptb_app.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            self.handle_attachment
        ))
        self.ptb_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_text
        ))

    def get_main_menu_kb(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Inbox", callback_data="menu_read"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ])

    def get_back_button(self):
        return [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]
 
    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        service = self.gmail.get_service()
        if not service: return
        try:
            results = service.users().messages().list(userId='me', q='is:unread', maxResults=3).execute()
            messages = results.get('messages', [])
 
            for msg in messages:
                m_id = msg['id']
                if m_id not in self.notified_emails:
                    msg_data = service.users().messages().get(userId='me', id=m_id, format='minimal').execute()
                    internal_date = int(msg_data.get('internalDate', 0))
 
                    if internal_date > self.boot_time:
                        self.notified_emails.add(m_id)
                        meta = self.gmail.get_email_metadata(m_id)
                        
                        text = (
                            f"🔔 *New Email Received!*\n\n"
                            f"👤 *From:* {meta['sender']}\n"
                            f"📝 *Subject:* {meta['subject']}\n"
                            f"📎 *Attachments:* Check inside.\n\n"
                            f"What would you like to do?"
                        )
                        kb = [
                            [InlineKeyboardButton("🤖 Generate Summary", callback_data=f"sum_{m_id}")],
                            [InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}")],
                            [InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{m_id}")]
                        ]
                        await context.bot.send_message(
                            chat_id=OWNER_TELEGRAM_ID,
                            text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                        )
        except Exception: pass
 
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
            if update.message:
                await update.message.reply_text(
                    "⚠️ *Authentication Required.*\nPlease connect your Gmail account to proceed.",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                )
            return
 
        text = "🎛️ *Workspace Dashboard*\nWelcome! What would you like to do today?"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())

    async def show_manual_inbox(self, message_obj, offset=0):
        service = self.gmail.get_service()
        if not service: return
        try:
            results = service.users().messages().list(userId='me', q='label:INBOX', maxResults=15).execute()
            messages = results.get('messages', [])
            if not messages:
                await message_obj.reply_text("📭 No emails found in Inbox.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                return
            
            page_msgs = messages[offset:offset+5]
            kb = []
            text = f"📥 *Manual Inbox (Emails {offset+1}-{offset+len(page_msgs)}):*\n\n"
            for idx, m in enumerate(page_msgs):
                meta = self.gmail.get_email_metadata(m['id'])
                safe_sender = html.escape(meta['sender'][:25])
                safe_subj = html.escape(meta['subject'][:30])
                text += f"*{idx+1+offset}.* {safe_sender}\n_{safe_subj}..._\n\n"
                kb.append([InlineKeyboardButton(f"📖 Read #{idx+1+offset}", callback_data=f"full_{m['id']}")])
            
            nav_buttons = []
            if offset >= 5: nav_buttons.append(InlineKeyboardButton("⬅️ Newer", callback_data=f"manual_read_{offset-5}"))
            if offset + 5 < len(messages): nav_buttons.append(InlineKeyboardButton("Older ➡️", callback_data=f"manual_read_{offset+5}"))
            
            if nav_buttons: kb.append(nav_buttons)
            kb.append(self.get_back_button())

            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            pass

    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(update.effective_user.id)
        await query.answer()
        data = query.data
 
        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            await query.edit_message_text("🎛️ *Workspace Dashboard*\nWelcome! What would you like to do today?", parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        elif data == "menu_read":
            kb = [self.get_back_button()]
            await query.edit_message_text("📥 *Inbox Mode*\nTell AI what you want to read. \n_Example: Any unread emails today?_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif data == "menu_compose":
            kb = [self.get_back_button()]
            await query.edit_message_text("✍️ *Compose Mode*\nTell AI your intent.\n_Example: Draft an email to HR for sick leave_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif data == "menu_search":
            kb = [self.get_back_button()]
            await query.edit_message_text("🔍 *Search*\nAsk AI to find specific emails.\n_Example: Find emails from Ali last week_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif data == "menu_settings":
            kb = [[InlineKeyboardButton("🔀 Switch to Manual Mode", callback_data="manual_read_0")], self.get_back_button()]
            await query.edit_message_text("⚙️ *Settings*\nConfigure your assistant.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith("manual_read_"):
            offset = int(data.split("_")[2])
            await self.show_manual_inbox(query.message, offset)
        elif data == "cancel_compose":
            self.compose_states.pop(user_id, None)
            await query.edit_message_text("❌ Action cancelled.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
        elif data == "send_manual_draft":
            state = self.compose_states.get(user_id)
            if state:
                await query.edit_message_text("⏳ Sending Email...")
                res = await asyncio.to_thread(self.gmail.send_email, state['to'], state['subj'], state['body'])
                self.compose_states.pop(user_id, None)
                await query.edit_message_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
        else:
            parts = data.split("_", 1)
            if len(parts) != 2: return
            action, m_id = parts
 
            if action == "sum":
                await query.edit_message_text("⏳ Generating AI Summary...")
                body = self.gmail.get_full_body(m_id)
                summary = await asyncio.to_thread(self.ai.get_summary, body)
                
                if summary.startswith("Error:") or "validation error" in summary.lower():
                    await query.edit_message_text("⚠️ *AI Quota Exhausted. Shifting to Manual Mode.*", parse_mode="Markdown")
                    await self.show_manual_inbox(query.message, 0)
                    return
                
                kb = [[InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}")], self.get_back_button()]
                await query.edit_message_text(f"🤖 *AI Summary:*\n\n{summary}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
 
            elif action == "full":
                await query.edit_message_text("⏳ Fetching...")
                body = self.gmail.get_full_body(m_id)
                meta = self.gmail.get_email_metadata(m_id)
                
                if len(body) > 3500: body = body[:3500] + "\n\n[Truncated]"
                
                safe_body = html.escape(body)
                safe_sender = html.escape(meta['sender'])
                safe_subject = html.escape(meta['subject'])
                
                url_pattern = re.compile(r'(https?://[^\s]+)')
                safe_body = url_pattern.sub(r'<a href="\1">🔗 Click Here</a>', safe_body)
                
                formatted_email = f"📧 <b>From:</b> {safe_sender}\n📝 <b>Subject:</b> {safe_subject}\n━━━━━━━━━━━━━━━━━━\n\n{safe_body}"
                
                kb = [
                    [InlineKeyboardButton("📥 Get Attachments", callback_data=f"getatt_{m_id}")],
                    [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{m_id}"), InlineKeyboardButton("🔄 Forward", callback_data=f"fw_{m_id}")],
                    [InlineKeyboardButton("🗑️ Trash", callback_data=f"del_{m_id}"), InlineKeyboardButton("🔙 Back to Inbox", callback_data="manual_read_0")]
                ]
                await query.edit_message_text(formatted_email, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
 
            elif action == "del":
                self.gmail.delete_email(m_id)
                await query.edit_message_text("🗑️ Email moved to trash.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                
            elif action == "reply":
                meta = self.gmail.get_email_metadata(m_id)
                sender_email = re.search(r'<(.+?)>', meta['sender']).group(1) if '<' in meta['sender'] else meta['sender']
                self.compose_states[user_id] = {'step': 'AWAIT_BODY', 'to': sender_email, 'subj': f"Re: {meta['subject']}"}
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                await query.edit_message_text(f"↩️ *Replying to {sender_email}*\n\nPlease type your message below. 📎 Attach a file if needed.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
            elif action == "getatt":
                await query.edit_message_text("📥 Attempting to fetch attachments (This feature utilizes email parsing)...", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                # Note: Full attachment fetching requires extra Gmail API logic mapping part IDs. AI will summarize otherwise.
 
    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        attachment = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not attachment: return
 
        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ *File is too large for Telegram (Max 20MB).* \nPlease upload it to your Google Drive and just paste the shareable link here. I will add the link to your email.", parse_mode="Markdown")
            return
 
        msg = await update.message.reply_text("⏳ Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)
        self.gmail.current_attachment = file_path

        # If user is in manual compose flow
        if user_id in self.compose_states and self.compose_states[user_id]['step'] == 'AWAIT_BODY':
            self.compose_states[user_id]['body'] += f"\n[Attachment: {file_name}]"
            kb = [[InlineKeyboardButton("✅ Send", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            state = self.compose_states[user_id]
            draft_text = f"📄 *Draft Ready!*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n📎 *1 File Attached*\n\nReview and click Send."
            await msg.edit_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await msg.edit_text(f"📎 *File '{file_name}' received.* \nWhat do you want to do with it?\n_Example: Forward this to HR_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
 
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
            
        text = update.message.text
        
        # State Machine for Manual Compose Flow
        if user_id in self.compose_states:
            state = self.compose_states[user_id]
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            
            if state['step'] == 'AWAIT_TO':
                state['to'] = text
                state['step'] = 'AWAIT_SUBJ'
                await update.message.reply_text(f"Got it. To: {text}\nWhat is the Subject?", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_SUBJ':
                state['subj'] = text
                state['step'] = 'AWAIT_BODY'
                await update.message.reply_text("Please type your email message. 📎 Attach a file if needed.", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_BODY':
                state['body'] = text
                kb_send = [[InlineKeyboardButton("✅ Send", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                draft_text = f"📄 *Final Draft:*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n\nReview and click Send."
                await update.message.reply_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_send))
            return
 
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = await asyncio.to_thread(self.ai.agent_chat, text, user_id)
        
        if res.startswith("Error:") or "validation error" in res.lower() or "quota" in res.lower():
            await update.message.reply_text("⚠️ *AI Quota exhausted. Shifting to Manual Mode.*", parse_mode="Markdown")
            await self.show_manual_inbox(update.message, 0)
        else:
            if "Wait!" in res and "file" in res.lower():
                await update.message.reply_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            else:
                await update.message.reply_text(res, reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
 
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID): return
        msg = await update.message.reply_text("🎙️ Processing voice note...")
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
            transcribed_text = await asyncio.to_thread(self.ai.transcribe_audio, file_path)
            if os.path.exists(file_path): os.remove(file_path)
 
            if not transcribed_text or transcribed_text.startswith("Transcription error"):
                await msg.edit_text("❌ Could not understand voice. Switching to manual mode.")
                await self.show_manual_inbox(msg, 0)
                return
 
            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing...", parse_mode="Markdown")
            res = await asyncio.to_thread(self.ai.agent_chat, transcribed_text, user_id)
            
            if res.startswith("Error:") or "validation error" in res.lower() or "quota" in res.lower():
                await msg.edit_text("⚠️ *AI Quota exhausted. Shifting to Manual Mode.*", parse_mode="Markdown")
                await self.show_manual_inbox(update.message, 0)
            else:
                await update.message.reply_text(res, reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")
 
    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        response = self.ai.guest_chat("Hello", user_id)
        if update.message: await update.message.reply_text(response)
        elif update.callback_query: await update.callback_query.message.reply_text(response)
 
bot_handler_instance = BotHandler()
 
@fastapi_app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_handler_instance.ptb_app.bot)
    await bot_handler_instance.ptb_app.process_update(update)
    return {"ok": True}
 
@fastapi_app.on_event("startup")
async def on_startup():
    await bot_handler_instance.ptb_app.initialize()
    try:
        await bot_handler_instance.ptb_app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await bot_handler_instance.ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print("✅ Webhook set successfully.")
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 2)
        await bot_handler_instance.ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    except Exception: pass

    bot_handler_instance.ptb_app.job_queue.run_repeating(
        bot_handler_instance.check_new_emails, interval=60, first=10
    )
    await bot_handler_instance.ptb_app.start()
 
@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await bot_handler_instance.ptb_app.stop()
 
if __name__ == "__main__":
    uvicorn.run("bot_handler:fastapi_app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
