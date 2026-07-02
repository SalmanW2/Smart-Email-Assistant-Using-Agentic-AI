import os
import re

file_path = 'backend/bot/telegram_handler.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. import dateparser
if 'import dateparser' not in content:
    content = content.replace('import re\n', 'import re\nimport dateparser\nfrom datetime import datetime, timedelta\n')

# 2. kb_settings v_map
content = re.sub(
    r'v_map = {"text": ".*?", "voice": ".*?", "both": ".*?"}',
    'v_map = {"text": "📝 Text Only", "voice": "🎙️ Voice Only", "smart": "🧠 Smart Routing"}',
    content
)

# 3. cycle_voice map
content = re.sub(
    r'cycle\s*=\s*{"text": "voice", "voice": "both", "both": "text"}',
    'cycle   = {"text": "voice", "voice": "smart", "smart": "text"}',
    content
)

# 4. kb_draft
new_kb_draft = '''def kb_draft(has_files: bool = False) -> InlineKeyboardMarkup:
    """Enhanced Draft UI with Dynamic Edit capabilities."""
    rows = [
        [InlineKeyboardButton("🚀 Send",       callback_data="send_draft"),
         InlineKeyboardButton("📅 Schedule",   callback_data="schedule_draft_manual")],
        [InlineKeyboardButton("✏️ Edit",       callback_data="edit_draft_hub"),
         InlineKeyboardButton("📎 Attach",     callback_data="attach_hint")],
        [InlineKeyboardButton("❌ Cancel",      callback_data="cancel")]
    ]
    if has_files:
        rows.insert(2, [InlineKeyboardButton("🗑️ Clear Files", callback_data="clear_att")])
        
    return InlineKeyboardMarkup(rows)'''

content = re.sub(r'def kb_draft\(has_files: bool = False\) -> InlineKeyboardMarkup:.*?(?=\n\n\w)', new_kb_draft, content, flags=re.DOTALL)

# 5. Smart routing & voice note captioning in _send
# We replace the whole `voice_pref = prefs.get("voice_preference", "text") ...` block down to `if is_voice_type ...`
send_block_target = '''        voice_pref = prefs.get("voice_preference", "text")

        if is_voice_type or voice_pref in ("voice", "both"):
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            # Remove markdown symbols to prevent TTS engine from reading punctuation aloud
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio = None
            try:
                try:
                    audio = await self.voice.synthesize(
                        clean_tts, telegram_id=uid,
                        preferred_method=prefs.get("preferred_tts_method", "google"))
                except Exception as tts_err:
                    logger.warning(f"TTS synthesis exception for user {uid}: {tts_err}")
                    audio = None
                    
                if audio and os.path.exists(audio):
                    with open(audio, "rb") as f:
                        try:
                            if voice_pref == "both":
                                await context.bot.send_voice(chat_id=uid, voice=f)
                                await self._edit(msg_obj, text, markup, parse_mode=parse_mode)
                            else:
                                await context.bot.send_voice(chat_id=uid, voice=f)
                                if update.message:
                                    try:
                                        await update.message.delete()
                                    except Exception:
                                        pass
                        except Exception as ve:
                            logger.error(f"Voice send error: {ve}")
                            await self._edit(msg_obj, text, markup, parse_mode=parse_mode)
            finally:
                if audio and os.path.exists(audio):
                    try:
                        os.remove(audio)
                    except Exception:
                        pass
        else:
            await self._edit(msg_obj, text, markup, parse_mode=parse_mode)'''

new_send_block = '''        voice_pref = prefs.get("voice_preference", "text")
        
        # --- Smart Voice Routing Heuristics ---
        if voice_pref == "smart":
            # Heuristics: if response is long or doesn't have UI cards, use voice
            if len(text_content) > 150 and "__SHOW_SEARCH_LIST__" not in raw:
                voice_pref = "voice"
            else:
                voice_pref = "text"

        if is_voice_type or voice_pref in ("voice", "both"):
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            # Remove markdown symbols to prevent TTS engine from reading punctuation aloud
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio = None
            try:
                try:
                    audio = await self.voice.synthesize(
                        clean_tts, telegram_id=uid,
                        preferred_method=prefs.get("preferred_tts_method", "google"))
                except Exception as tts_err:
                    logger.warning(f"TTS synthesis exception for user {uid}: {tts_err}")
                    audio = None
                    
                if audio and os.path.exists(audio):
                    with open(audio, "rb") as f:
                        try:
                            if voice_pref == "voice" or is_voice_type:
                                # Voice Note Captioning!
                                first_sentence = clean_tts.split('.')[0] if '.' in clean_tts else "Voice Response"
                                caption = f"🎙️ {first_sentence[:50]}..."
                                await context.bot.send_voice(chat_id=uid, voice=f, caption=caption)
                                if update.message:
                                    try:
                                        await update.message.delete()
                                    except Exception:
                                        pass
                            else:
                                await context.bot.send_voice(chat_id=uid, voice=f)
                                await self._edit(msg_obj, text, markup, parse_mode=parse_mode)
                        except Exception as ve:
                            logger.error(f"Voice send error: {ve}")
                            await self._edit(msg_obj, text, markup, parse_mode=parse_mode)
            finally:
                if audio and os.path.exists(audio):
                    try:
                        os.remove(audio)
                    except Exception:
                        pass
        else:
            await self._edit(msg_obj, text, markup, parse_mode=parse_mode)'''

content = content.replace(send_block_target, new_send_block)


# 6. Strict manual fallback interceptors

# In handle_text:
ai_fallback_text = '''
            # --- AI Strict Manual Fallback Guard ---
            prefs = await self._prefs(uid)
            if not prefs.get("ai_mode_enabled", True) and uid not in self.compose_states and not self.search_states.get(uid):
                await update.message.reply_text("🤖 *AI Mode is currently OFF.*\n\nPlease use the /menu buttons to navigate manually, or turn on AI Mode in Settings to chat naturally.", parse_mode="Markdown")
                return
'''

content = content.replace('msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")', ai_fallback_text + '\n            msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")')

# In handle_voice:
ai_fallback_voice = '''
        # --- AI Strict Manual Fallback Guard ---
        prefs = await self._prefs(uid)
        if not prefs.get("ai_mode_enabled", True) and uid not in self.compose_states:
            await update.message.reply_text("🤖 *AI Mode is currently OFF.*\n\nPlease use the /menu buttons to navigate manually, or turn on AI Mode in Settings to chat naturally.", parse_mode="Markdown")
            return
'''
content = content.replace('msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")', ai_fallback_voice + '\n        msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")')


# 7. AWAIT_SCHEDULE_TIME interceptor in handle_text
await_sch_block = '''
            if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_SCHEDULE_TIME":
                parsed = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})
                if not parsed:
                    await update.message.reply_text("I couldn't understand that time format. Please try again (e.g., 'tomorrow at 3pm' or '2026-07-03 15:00').")
                    return
                    
                state = self.compose_states[uid]
                try:
                    await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").insert({
                        "telegram_id": uid,
                        "to_email": state["to"],
                        "subject": state.get("subj", "No Subject"),
                        "body": state.get("body", ""),
                        "scheduled_time": parsed.strftime("%Y-%m-%d %H:%M:%S")
                    }).execute())
                    self.compose_states.pop(uid, None)
                    await update.message.reply_text("✅ *Email Scheduled Successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
                except Exception as e:
                    logger.error(f"Manual schedule error: {e}")
                    await update.message.reply_text("❌ Failed to schedule.")
                return
'''
# inject before `if self.search_states.get(uid) == "AWAIT_QUERY":`
content = content.replace('if self.search_states.get(uid) == "AWAIT_QUERY":', await_sch_block + '\n            if self.search_states.get(uid) == "AWAIT_QUERY":')


# 8. Schedule draft manual callback in handle_button
sch_callback_block = '''
        if action == "schedule_draft_manual":
            self.compose_states[uid]["step"] = "AWAIT_SCHEDULE_TIME"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ In 1 Hour", callback_data="sch_time_1h"),
                 InlineKeyboardButton("🌅 Tomorrow Morning", callback_data="sch_time_tmrw")],
                [InlineKeyboardButton("🔙 Back to Draft", callback_data="restore_draft_view")]
            ])
            await query.edit_message_text(
                "📅 *Schedule Email*\n\nWhen would you like to send this? Type a time (e.g. 'tomorrow at 3pm') or use a quick button below:",
                parse_mode="Markdown", reply_markup=kb)
            return
            
        if action.startswith("sch_time_"):
            if uid not in self.compose_states: return
            if action == "sch_time_1h":
                t = datetime.now() + timedelta(hours=1)
            elif action == "sch_time_tmrw":
                t = datetime.now() + timedelta(days=1)
                t = t.replace(hour=9, minute=0, second=0)
            
            state = self.compose_states[uid]
            try:
                await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").insert({
                    "telegram_id": uid,
                    "to_email": state["to"],
                    "subject": state.get("subj", "No Subject"),
                    "body": state.get("body", ""),
                    "scheduled_time": t.strftime("%Y-%m-%d %H:%M:%S")
                }).execute())
                self.compose_states.pop(uid, None)
                await query.edit_message_text("✅ *Email Scheduled Successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
            except Exception as e:
                logger.error(f"Manual schedule error: {e}")
                await query.answer("❌ Failed to schedule.", show_alert=True)
            return
'''

content = content.replace('        if action == "send_draft":', sch_callback_block + '\n        if action == "send_draft":')


with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched successfully!")
