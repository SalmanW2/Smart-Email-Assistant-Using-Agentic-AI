import os
import sys

filepath = 'backend/bot/telegram_handler.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

target = """        if action == "cancel":
            for fp in (self.compose_states.pop(uid, {}) or {}).get("attachments", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            self._clear_history(uid)
            await query.edit_message_text(
                "🚫 *Canceled.*\\n\\nReturning to dashboard.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
            return"""

cancel_sch_block = """        if action == "cancel_sch":
            sch_id = args[0] if args else ""
            if sch_id:
                try:
                    await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").delete().eq("id", sch_id).execute())
                    await query.edit_message_text(
                        "🚫 *Scheduled Email Canceled.*\\n\\nThe email will not be sent.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]])
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to cancel schedule {sch_id}: {e}")
                    await query.answer("❌ Failed to cancel schedule.", show_alert=True)
            return"""

if target in content:
    content = content.replace(target, target + "\n\n" + cancel_sch_block)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("PATCHED SUCCESSFULLY")
else:
    print("TARGET NOT FOUND. Content might be different.")
