import re

with open('backend/bot/telegram_handler.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_handlers = """
        if action == "list_sch":
            try:
                res = await self.db.db.run(
                    lambda: self.db.db.client.table("scheduled_emails")
                            .select("*").eq("telegram_id", uid).eq("status", "pending")
                            .order("scheduled_time", desc=False).execute())
                
                tasks = getattr(res, "data", []) or []
                if not tasks:
                    await query.edit_message_text(
                        "📭 *No Scheduled Emails*\n\nYou have no pending scheduled emails.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu_main")]])
                    )
                    return
                
                text = "📅 *Your Scheduled Emails:*\n\n"
                kb_rows = []
                for idx, task in enumerate(tasks, 1):
                    t_time = task.get('scheduled_time', 'Unknown')
                    t_sub = task.get('subject', 'No Subject')
                    text += f"*{idx}.* `{t_time}`\n    _Sub:_ {t_sub}\n\n"
                    kb_rows.append([InlineKeyboardButton(f"❌ Cancel #{idx}", callback_data=f"cancel_sch:{task['id']}")])
                
                kb_rows.append([InlineKeyboardButton("🔙 Menu", callback_data="menu_main")])
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))
            except Exception as e:
                logger.error(f"Failed to list scheduled emails: {e}")
                await query.answer("❌ Failed to retrieve scheduled emails.", show_alert=True)
            return

        if action == "confirm_sch":
            await query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
            await query.answer("✅ Schedule Confirmed!", show_alert=False)
            return

        if action == "edit_sch_time":
            await query.answer("🎙️ To edit the time, simply send a voice note or text saying 'Reschedule it to tomorrow at 5 PM'.", show_alert=True)
            return

        if action == "edit_sch_draft":
            await query.answer("🎙️ To edit the draft, just tell me 'Change the subject of my scheduled email to X'.", show_alert=True)
            return
"""

# Insert right before cancel_sch
content = content.replace('        if action == "cancel_sch":', new_handlers + '\n        if action == "cancel_sch":')

with open('backend/bot/telegram_handler.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Injected scheduled email handlers!")
