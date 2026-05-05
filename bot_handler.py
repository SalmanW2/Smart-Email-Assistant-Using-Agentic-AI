import os
import time
import uvicorn
import asyncio
import re
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
        self.navigation_history = {} 
        self.active_voice_tasks = set()
        self.pending_sends = {}
        
        self.email_lock = asyncio.Lock()

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

    # FIXED: A centralized helper function to handle login prompts and track message ID
    async def request_login(self, update: Update):
        link = self.auth.get_login_link()
        kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
        text = "⚠️ *Please login first!*\nYou need to connect your Google Account to proceed."
        
        if update.callback_query:
            msg = await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            self.auth.last_login_msg_id = update.callback_query.message.message_id
        elif update.message:
            msg = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            self.auth.last_login_msg_id = msg.message_id

    def get_main_menu_kb(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ])

    def get_back_button(self, context_type="main", extra_data=""):
        if context_type == "inbox":
            return [InlineKeyboardButton("🔙 Back to Inbox", callback_data=f"manual_read_{extra_data}")]
        elif context_type == "search":
            return [InlineKeyboardButton("🔙 Back to Results", callback_data=f"page_read_{extra_data}")]
        return [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]

    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            await asyncio.to_thread(urllib.request.urlopen, WEBHOOK_URL)
        except Exception: pass

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.email_lock:
            service = self.gmail.get_service()
            if not service: return
            try:
                results = service.users().messages().list(userId='me', q='is:unread', maxResults=3).execute()
                messages = results.get('messages', [])

                for msg in messages:
                    m_id = msg['id']
                    if m_id not in self.notified_emails:
                        self.notified_emails.add(m_id)
                        
                        msg_data = service.users().messages().get(userId='me', id=m_id, format='minimal').execute()
                        internal_date = int(msg_data.get('internalDate', 0))

                        if internal_date > self.startup_time:
                            meta = self.gmail.get_email_metadata(m_id)
                            att_count = len(meta.get('attachments', []))
                            att_text = f"\n📎 *Attachments:* {att_count} File(s) enclosed." if att_count > 0 else ""
                            
                            text = (
                                f"🔔 *New Email Received!*\n\n"
                                f"👤 *From:* {meta['sender']}\n"
                                f"📝 *Subject:* {meta['subject']}"
                                f"{att_text}"
                            )
                            kb = [
                                [InlineKeyboardButton("🤖 Generate Summary", callback_data=f"sum_{m_id}")],
                                [InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}_main")],
                                [InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{m_id}_main")]
                            ]
                            await context.bot.send_message(
                                chat_id=OWNER_TELEGRAM_ID,
                                text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                            )
            except Exception: pass

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID): return

        if not self.gmail.get_service():
            await self.request_login(update)
            return

        text = "🎛️ *Workspace Dashboard*\nSelect an action below or type your request."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())

    async def send_attachment_dashboard(self, message_obj, user_id):
        files = self.gmail.get_user_attachments(user_id)
        if not files:
            text = "📭 *Memory Empty:* No attachments saved."
            kb = [self.get_back_button()]
            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return

        text = f"📁 *File(s) Saved to Memory*\nTotal Files: {len(files)}\n\n"
        text += "💡 *Tip for AI:* To send these files using the AI, simply send a voice or text message saying: _'Send an email to Ali and attach the files.'_\n\n"
        
        kb = []
        for i, f in enumerate(files):
            safe_filename = os.path.basename(f).replace("_", "-").replace("*", "")
            text += f"*{i+1}.* `{safe_filename}`\n"
            kb.append([InlineKeyboardButton(f"❌ Remove File {i+1}", callback_data=f"rm_att_{i}")])
        
        kb.append([InlineKeyboardButton("➕ Add Another Attachment", callback_data="add_att")])
        kb.append([
            InlineKeyboardButton("🧹 Clear All", callback_data="clr_att"), 
            InlineKeyboardButton("✉️ Draft Email", callback_data="menu_compose")
        ])
        kb.append(self.get_back_button())

        if hasattr(message_obj, 'edit_text'):
            await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def render_full_email(self, query, m_id, nav_context, nav_offset):
        await query.edit_message_text("⏳ Fetching...")
        body = self.gmail.get_full_body(m_id)
        meta = self.gmail.get_email_metadata(m_id)
        
        if len(body) > 3500: body = body[:3500] + "\n\n[Truncated]"
        
        safe_body = body.replace('<', '').replace('>', '') 
        safe_sender = meta['sender'].replace('<', '').replace('>', '')
        safe_subject = meta['subject'].replace('<', '').replace('>', '')
        
        url_pattern = re.compile(r'(https?://[^\s]+)')
        safe_body = url_pattern.sub(r'<a href="\1">🔗 Click Here</a>', safe_body)
        
        att_count = len(meta.get('attachments', []))
        att_text = f"\n📎 <b>Attachments:</b> {att_count} File(s) ({', '.join(meta['attachments'])})" if att_count > 0 else ""
        
        formatted_email = f"📧 <b>From:</b> {safe_sender}\n📝 <b>Subject:</b> {safe_subject}{att_text}\n━━━━━━━━━━━━━━━━━━\n\n{safe_body}"
        
        kb = []
        kb.append([InlineKeyboardButton("📥 Get Attachments", callback_data=f"getatt_{m_id}_{nav_context}")])
        kb.append([InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{m_id}_{nav_context}"), InlineKeyboardButton("🗑️ Trash", callback_data=f"del_{m_id}_{nav_context}")])
        kb.append(self.get_back_button(nav_context, nav_offset))
        
        await query.edit_message_text(formatted_email, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    async def send_ai_response(self, message_obj, res_text, user_id):
        kb = []
        has_pending = user_id in self.gmail.pending_ai_sends
        if has_pending:
            kb.append([InlineKeyboardButton("↩️ Undo Send", callback_data="undosend_ai")])
        kb.append(self.get_back_button())
        
        sent_msg = await message_obj.edit_text(res_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        if has_pending:
            async def process_ai_send():
                await asyncio.sleep(7)
                if user_id in self.gmail.pending_ai_sends:
                    draft = self.gmail.pending_ai_sends.pop(user_id)
                    res = await asyncio.to_thread(self.gmail.send_email, draft['to'], draft['subj'], draft['body'], [], user_id=user_id)
                    try:
                        new_kb = [self.get_back_button()]
                        await sent_msg.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))
                    except: pass
            asyncio.create_task(process_ai_send())

    async def show_paginated_emails(self, message_obj, query='label:INBOX', offset=0, user_id=None, is_search=False):
        service = self.gmail.get_service()
        if not service: return
        try:
            if user_id:
                self.current_queries[user_id] = query
                self.navigation_history[user_id] = {'type': 'search' if is_search else 'inbox', 'offset': offset}

            results = service.users().messages().list(userId='me', q=query, maxResults=30).execute()
            messages = results.get('messages', [])
            
            if not messages:
                text = f"📭 No emails found for: `{query}`"
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
            header_text = f"🔍 Searched: `{query}`" if is_search else f"📥 Inbox"
            text = f"*{header_text} ({offset+1}-{offset+len(page_msgs)}):*\n\n"
            
            context_tag = "search" if is_search else "inbox"
            
            for idx, m in enumerate(page_msgs):
                meta = self.gmail.get_email_metadata(m['id'])
                safe_sender = meta['sender'][:30].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                safe_subj = meta['subject'][:35].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                
                text += f"*{idx+1+offset}.* {safe_sender}\n_{safe_subj}..._\n\n"
                kb.append([InlineKeyboardButton(f"📖 Read #{idx+1+offset}", callback_data=f"full_{m['id']}_{context_tag}")])
            
            nav_buttons = []
            prefix = "page_read_" if is_search else "manual_read_"
            if offset >= 5: 
                nav_buttons.append(InlineKeyboardButton("⬅️ Newer", callback_data=f"{prefix}{offset-5}"))
            if offset + 5 < len(messages): 
                nav_buttons.append(InlineKeyboardButton("Older ➡️", callback_data=f"{prefix}{offset+5}"))
            
            if nav_buttons: kb.append(nav_buttons)
            kb.append(self.get_back_button())

            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
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

        if not self.gmail.get_service() and data not in ["action_logout"]:
            await self.request_login(update)
            return

        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            self.navigation_history.pop(user_id, None)
            text = "🎛️ *Workspace Dashboard*\nSelect an action below or type your request."
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        
        elif data == "menu_compose":
            self.compose_states[user_id] = {'step': 'AWAIT_TO', 'to': '', 'subj': '', 'body': '', 'attachments': []}
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
            if os.path.exists(self.auth.token_file): os.remove(self.auth.token_file)
            self.auth.cached_creds = None
            self.gmail.service = None
            await query.edit_message_text("✅ *Logged out successfully.*\n\nSend /start to connect a new Google Account.", parse_mode="Markdown")

        elif data.startswith("manual_read_"):
            offset = int(data.split("_")[2])
            await self.show_paginated_emails(query.message, query='label:INBOX', offset=offset, user_id=user_id, is_search=False)
        
        elif data.startswith("page_read_"):
            offset = int(data.split("_")[2])
            active_query = self.current_queries.get(user_id, 'label:INBOX')
            await self.show_paginated_emails(query.message, query=active_query, offset=offset, user_id=user_id, is_search=True)
        
        elif data == "cancel_compose":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            await query.edit_message_text("🚫 *Process Canceled*\n\nThe action was safely terminated. How else may I assist you?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
        
        elif data.startswith("cancel_voice_"):
            task_id = data.split("_")[2]
            if task_id in self.active_voice_tasks:
                self.active_voice_tasks.remove(task_id)
            await query.edit_message_text("🚫 *Process Canceled*\n\nThe voice command execution was halted successfully.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data.startswith("rm_att_"):
            idx = int(data.split("_")[2])
            files = self.gmail.get_user_attachments(user_id)
            if idx < len(files):
                fp = files.pop(idx)
                if os.path.exists(fp): os.remove(fp)
            await self.send_attachment_dashboard(query.message, user_id)

        elif data == "clr_att":
            self.gmail.clear_user_attachments(user_id)
            await query.edit_message_text("🧹 *All attachments have been securely wiped from memory.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "add_att":
            await query.edit_message_text("📎 *Please upload the next file directly in this chat.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "send_manual_draft":
            state = self.compose_states.get(user_id)
            if state:
                self.pending_sends[user_id] = state
                kb = [[InlineKeyboardButton("↩️ Undo Send", callback_data="undosend_manual")], self.get_back_button()]
                msg = await query.edit_message_text("⏳ *Email queued.* Sending in 7 seconds...", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
                async def process_manual_send():
                    await asyncio.sleep(7)
                    if user_id in self.pending_sends:
                        draft = self.pending_sends.pop(user_id)
                        res = await asyncio.to_thread(self.gmail.send_email, draft['to'], draft['subj'], draft['body'], draft['attachments'], user_id=user_id)
                        self.compose_states.pop(user_id, None)
                        try:
                            await msg.edit_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                        except: pass
                asyncio.create_task(process_manual_send())

        elif data == "undosend_manual":
            if user_id in self.pending_sends:
                self.pending_sends.pop(user_id)
                self.compose_states.pop(user_id, None)
            await query.edit_message_text("🚫 *Send Canceled.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "undosend_ai":
            if user_id in self.gmail.pending_ai_sends:
                self.gmail.pending_ai_sends.pop(user_id)
            await query.edit_message_text("🚫 *AI Send Canceled.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        else:
            parts = data.split("_")
            if len(parts) < 2: return
            action = parts[0]
            m_id = parts[1]
            
            nav_context = parts[2] if len(parts) > 2 else "main"
            nav_offset = str(self.navigation_history.get(user_id, {}).get('offset', 0))

            if action == "sum":
                await query.edit_message_text("⏳ Generating AI Summary...")
                body = self.gmail.get_full_body(m_id)
                meta = self.gmail.get_email_metadata(m_id)
                summary = await asyncio.to_thread(self.ai.get_summary, body, meta['sender'])
                
                if summary.startswith("Error:"):
                    await query.edit_message_text(f"⚠️ System Alert: {summary}")
                    return
                
                kb = [[InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}_{nav_context}")], self.get_back_button(nav_context, nav_offset)]
                await query.edit_message_text(f"🤖 *AI Summary:*\n\n{summary}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

            elif action == "full":
                await self.render_full_email(query, m_id, nav_context, nav_offset)

            elif action == "del":
                self.gmail.delete_email(m_id)
                kb = [
                    [InlineKeyboardButton("↩️ Undo Delete", callback_data=f"undodel_{m_id}_{nav_context}")],
                    self.get_back_button(nav_context, nav_offset)
                ]
                await query.edit_message_text("🗑️ *Email moved to trash.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
                async def remove_del_undo():
                    await asyncio.sleep(7)
                    try:
                        new_kb = [self.get_back_button(nav_context, nav_offset)]
                        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))
                    except: pass
                asyncio.create_task(remove_del_undo())
            
            elif action == "undodel":
                self.gmail.untrash_email(m_id)
                await self.render_full_email(query, m_id, nav_context, nav_offset)
                
            elif action == "reply":
                meta = self.gmail.get_email_metadata(m_id)
                sender_email = re.search(r'<(.+?)>', meta['sender']).group(1) if '<' in meta['sender'] else meta['sender']
                self.compose_states[user_id] = {'step': 'AWAIT_BODY', 'to': sender_email, 'subj': f"Re: {meta['subject']}", 'attachments': []}
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                await query.edit_message_text(f"↩️ *Replying to {sender_email}*\n\nPlease type your message below. 📎 You can attach a file in the next step.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
            elif action == "getatt":
                await query.edit_message_text("⏳ Fetching attachments...")
                file_paths = await asyncio.to_thread(self.gmail.get_attachments, m_id)
                
                back_to_email_kb = [[InlineKeyboardButton("🔙 Back to Email", callback_data=f"full_{m_id}_{nav_context}")]]
                
                if not file_paths:
                    await query.edit_message_text("📭 *No attachments found in this specific email.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back_to_email_kb))
                else:
                    await query.edit_message_text("📤 Sending attachments, please wait...")
                    for fp in file_paths:
                        with open(fp, 'rb') as f:
                            await context.bot.send_document(chat_id=user_id, document=f)
                        os.remove(fp)
                    await query.edit_message_text("✅ Attachments sent successfully!", reply_markup=InlineKeyboardMarkup(back_to_email_kb))

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID): return

        # FIXED: Check login before processing attachments!
        if not self.gmail.get_service():
            await self.request_login(update)
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

        if user_id in self.compose_states and self.compose_states[user_id]['step'] == 'AWAIT_ATTACHMENT':
            self.compose_states[user_id]['attachments'].append(file_path)
            state = self.compose_states[user_id]
            kb = [[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            
            files_list = "\n".join([f"- {os.path.basename(f).replace('_', '-')}" for f in state['attachments']])
            draft_text = f"📄 *Draft Ready!*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n📎 *Attachments:* \n{files_list}\n\nYou can upload more files or click Send Now."
            await msg.edit_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            self.gmail.add_user_attachment(user_id, file_path)
            await self.send_attachment_dashboard(msg, user_id)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID): return
            
        if not self.gmail.get_service():
            await self.request_login(update)
            return

        text = update.message.text
        
        if user_id in self.search_states and self.search_states[user_id] == 'AWAIT_QUERY':
            query_text = text
            self.search_states.pop(user_id, None)
            waiting_msg = await update.message.reply_text(f"🔍 Searching for: `{query_text}`...", parse_mode="Markdown")
            await self.show_paginated_emails(waiting_msg, query=query_text, offset=0, user_id=user_id, is_search=True)
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
            msg_obj = await update.message.reply_text("⏳ Processing...")
            await self.send_ai_response(msg_obj, res, user_id)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID): return
        
        if not self.gmail.get_service():
            await self.request_login(update)
            return

        msg = await update.message.reply_text("🎙️ Processing voice note...")
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
            transcribed_text = await asyncio.to_thread(self.ai.transcribe_audio, file_path)
            if os.path.exists(file_path): os.remove(file_path)

            if transcribed_text.startswith("System Error:") or "[Audio Unclear]" in transcribed_text:
                await msg.edit_text(f"⚠️ *Transcription Error:*\nThe audio was unclear or cut off. Could you please repeat that professionally?", parse_mode="Markdown")
                return
            
            task_id = str(int(time.time() * 1000))
            self.active_voice_tasks.add(task_id)

            kb = [[InlineKeyboardButton("❌ Cancel Process", callback_data=f"cancel_voice_{task_id}")]]
            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing...", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

            res = await asyncio.to_thread(self.ai.agent_chat, transcribed_text, user_id)
            
            if task_id not in self.active_voice_tasks:
                return 
            self.active_voice_tasks.remove(task_id)

            if res.startswith("Error:"):
                await msg.edit_text(f"⚠️ System Alert: {res}")
            else:
                await self.send_ai_response(msg, res, user_id)
        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")

bot_handler_instance = BotHandler()

@fastapi_app.on_event("startup")
async def on_startup():
    if getattr(fastapi_app.state, "bot_initialized", False):
        return
    fastapi_app.state.bot_initialized = True
    
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
    try:
        if bot_handler_instance.ptb_app.running:
            await bot_handler_instance.ptb_app.stop()
            await bot_handler_instance.ptb_app.shutdown()
            print("✅ Bot shutdown gracefully.")
    except RuntimeError as e:
        print(f"ℹ️ Bot shutdown note: {e}")
    except Exception as e:
        print(f"⚠️ Shutdown Error: {e}")

@fastapi_app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_handler_instance.ptb_app.bot)
        await bot_handler_instance.ptb_app.process_update(update)
        return {"ok": True}
    except Exception:
        return {"ok": False}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("bot_handler:fastapi_app", host="0.0.0.0", port=port)