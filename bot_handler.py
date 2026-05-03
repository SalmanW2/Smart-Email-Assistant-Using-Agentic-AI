import os
import time
import uvicorn
import asyncio
import re
import html
import urllib.request
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                           MessageHandler, filters, ContextTypes)
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
        self.startup_time = int(time.time() * 1000)
        
        self.compose_states = {} 
        self.search_states = {}
        self.current_queries = {}

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
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ])

    def get_back_button(self):
        return [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]

    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            await asyncio.to_thread(urllib.request.urlopen, WEBHOOK_URL)
        except Exception:
            pass

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

                    if internal_date > self.startup_time:
                        self.notified_emails.add(m_id)
                        meta = self.gmail.get_email_metadata(m_id)
                        
                        text = (
                            f"🔔 *New Email Received!*\n\n"
                            f"👤 *From:* {meta['sender']}\n"
                            f"📝 *Subject:* {meta['subject']}\n"
                            f"📎 *Attachments:* Available in Inbox.\n\n"
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

        text = "🎛️ *Workspace Dashboard*\nSelect an action below or type your request."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())

    async def show_paginated_emails(self, message_obj, query='label:INBOX', offset=0, user_id=None):
        service = self.gmail.get_service()
        if not service: return
        try:
            if user_id:
                self.current_queries[user_id] = query

            results = service.users().messages().list(userId='me', q=query, maxResults=30).execute()
            messages = results.get('messages', [])
            
            if not messages:
                text = f"📭 No emails found for query: `{query}`"
                kb = [[InlineKeyboardButton("🔍 Search Again", callback_data="menu_search_prompt")], self.get_back_button()]
                if hasattr(message_obj, 'edit_text'):
                    await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                else:
                    await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return
            
            page_msgs = messages[offset:offset+5]
            if not page_msgs:
                await message_obj.reply_text("No more emails found.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                return

            kb = []
            text = f"📥 *Results ({offset+1}-{offset+len(page_msgs)}):*\nQuery: `{query}`\n\n"
            for idx, m in enumerate(page_msgs):
                meta = self.gmail.get_email_metadata(m['id'])
                safe_sender = html.escape(meta['sender'][:25])
                safe_subj = html.escape(meta['subject'][:30])
                text += f"*{idx+1+offset}.* {safe_sender}\n_{safe_subj}..._\n\n"
                kb.append([InlineKeyboardButton(f"📖 Read #{idx+1+offset}", callback_data=f"full_{m['id']}")])
            
            nav_buttons = []
            if offset >= 5: 
                nav_buttons.append(InlineKeyboardButton("⬅️ Newer", callback_data=f"page_read_{offset-5}"))
            if offset + 5 < len(messages): 
                nav_buttons.append(InlineKeyboardButton("Older ➡️", callback_data=f"page_read_{offset+5}"))
            
            if nav_buttons: kb.append(nav_buttons)
            kb.append(self.get_back_button())

            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            # FIXED: Handle errors so it doesn't crash silently
            error_text = f"⚠️ *Search Error:*\n{str(e)}"
            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(error_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            else:
                await message_obj.reply_text(error_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(update.effective_user.id)
        await query.answer()
        data = query.data

        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            text = "🎛️ *Workspace Dashboard*\nSelect an action below or type your request."
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        
        elif data == "menu_compose":
            self.compose_states[user_id] = {'step': 'AWAIT_TO', 'to': '', 'subj': '', 'body': ''}
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            await query.edit_message_text("✍️ *Manual Compose*\n\nPlease enter the recipient's email address:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "menu_search_prompt":
            self.search_states[user_id] = 'AWAIT_QUERY'
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            await query.edit_message_text("🔍 *Manual Search*\n\nPlease type your search query below.\n_(Examples: 'from:ali', 'is:unread', or a simple keyword)_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "menu_settings":
            kb = [
                [InlineKeyboardButton("🚪 Logout Account", callback_data="action_logout")],
                self.get_back_button()
            ]
            await query.edit_message_text("⚙️ *Settings*\n\nConfigure your assistant or logout of your Google account.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "action_logout":
            if os.path.exists(self.auth.token_file):
                os.remove(self.auth.token_file)
            self.auth.cached_creds = None
            self.gmail.service = None
            await query.edit_message_text("✅ *Logged out successfully.*\n\nSend /start to connect a new Google Account.", parse_mode="Markdown")

        elif data == "manual_read_0":
            await self.show_paginated_emails(query.message, query='label:INBOX', offset=0, user_id=user_id)
        
        elif data.startswith("page_read_"):
            offset = int(data.split("_")[2])
            active_query = self.current_queries.get(user_id, 'label:INBOX')
            await self.show_paginated_emails(query.message, query=active_query, offset=offset, user_id=user_id)
        
        elif data == "cancel_compose":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
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
                meta = self.gmail.get_email_metadata(m_id)
                
                # FIXED: Passing sender to the summary function
                summary = await asyncio.to_thread(self.ai.get_summary, body, meta['sender'])
                
                if summary.startswith("Error:"):
                    await query.edit_message_text(f"⚠️ System Alert: {summary}")
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
                    [InlineKeyboardButton("🗑️ Trash", callback_data=f"del_{m_id}"), InlineKeyboardButton("🔙 Back to Results", callback_data="manual_read_0")]
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
                await query.edit_message_text(f"↩️ *Replying to {sender_email}*\n\nPlease type your message below. 📎 You can attach a file in the next step.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
            elif action == "getatt":
                await query.edit_message_text("📥 Attempting to fetch attachments (This feature utilizes email parsing)...", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return

        attachment = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not attachment: return

        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ *File is too large for Telegram (Max 20MB).* \nPlease upload it to your Google Drive and paste the shareable link here.", parse_mode="Markdown")
            return

        msg = await update.message.reply_text("⏳ Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)
        self.gmail.current_attachment = file_path

        if user_id in self.compose_states and self.compose_states[user_id]['step'] == 'AWAIT_ATTACHMENT':
            self.compose_states[user_id]['body'] += f"\n\n[Attachment: {file_name}]"
            kb = [[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            state = self.compose_states[user_id]
            draft_text = f"📄 *Draft Ready!*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n📎 *1 File Attached*\n\nReview and click Send Now."
            await msg.edit_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await msg.edit_text(f"📎 *File '{file_name}' received.* \nWhat do you want to do with it? Just type your request.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
            
        text = update.message.text
        
        # FIXED: Bug in search where it tried to edit the user's message and failed silently.
        if user_id in self.search_states and self.search_states[user_id] == 'AWAIT_QUERY':
            query_text = text
            self.search_states.pop(user_id, None)
            waiting_msg = await update.message.reply_text(f"🔍 Searching for: `{query_text}`...", parse_mode="Markdown")
            await self.show_paginated_emails(waiting_msg, query=query_text, offset=0, user_id=user_id)
            return

        if user_id in self.compose_states:
            state = self.compose_states[user_id]
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            
            if state['step'] == 'AWAIT_TO':
                state['to'] = text
                state['step'] = 'AWAIT_SUBJ'
                await update.message.reply_text(f"Got it. To: {text}\n\nWhat is the Subject?", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_SUBJ':
                state['subj'] = text
                state['step'] = 'AWAIT_BODY'
                await update.message.reply_text("Please type your email message.", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_BODY':
                state['body'] = text
                state['step'] = 'AWAIT_ATTACHMENT'
                kb_send = [[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                draft_text = f"📄 *Draft Generated:*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n\n📎 Do you want to add an attachment? Upload the file now. If no attachment is needed, simply click *Send Now*."
                await update.message.reply_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_send))
            elif state['step'] == 'AWAIT_ATTACHMENT':
                await update.message.reply_text("Please upload an attachment file, or click Send Now if you are ready.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]))
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = await asyncio.to_thread(self.ai.agent_chat, text, user_id)
        
        if res.startswith("Error:"):
            await update.message.reply_text(f"⚠️ System Alert: {res}")
        else:
            # We enforce standard Markdown from AI, safely handled here
            if "Wait!" in res and "file" in res.lower():
                await update.message.reply_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            else:
                await update.message.reply_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

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

            if transcribed_text.startswith("Error:"):
                await msg.edit_text(f"⚠️ System Alert: {transcribed_text}")
                return

            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing...", parse_mode="Markdown")
            res = await asyncio.to_thread(self.ai.agent_chat, transcribed_text, user_id)
            
            if res.startswith("Error:"):
                await msg.edit_text(f"⚠️ System Alert: {res}")
            else:
                await update.message.reply_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")

    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        response = self.ai.guest_chat("Hello", user_id)
        if update.message: await update.message.reply_text(response)
        elif update.callback_query: await update.callback_query.message.reply_text(response)

bot_handler_instance = BotHandler()

@fastapi_app.on_event("startup")
async def on_startup():
    await bot_handler_instance.ptb_app.initialize()
    try:
        await bot_handler_instance.ptb_app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await bot_handler_instance.ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print("✅ Webhook synchronized successfully.")
    except Exception as e:
        print(f"⚠️ Webhook Error: {e}")

    bot_handler_instance.ptb_app.job_queue.run_repeating(
        bot_handler_instance.check_new_emails, interval=60, first=10
    )
    bot_handler_instance.ptb_app.job_queue.run_repeating(
        bot_handler_instance.auto_ping, interval=840, first=60
    )

    await bot_handler_instance.ptb_app.start()
    print("✅ Bot is fully initialized and online.")

@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await bot_handler_instance.ptb_app.stop()
    await bot_handler_instance.ptb_app.shutdown()

@fastapi_app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_handler_instance.ptb_app.bot)
        await bot_handler_instance.ptb_app.process_update(update)
        return {"ok": True}
    except RuntimeError as e:
        if "not initialized" in str(e).lower():
            return Response(content="Initializing", status_code=503)
        raise e
    except Exception as e:
        return {"ok": False}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("bot_handler:fastapi_app", host="0.0.0.0", port=port)
