# ───────────────────────────────────────────────
# withdraw panel
# ───────────────────────────────────────────────
@app.on_message(filters.private & filters.regex("^📤"))
async def withdraw_panel(_, m):
    uid = m.from_user.id
    u = users.find_one({"user_id": uid}) or {}

    users.update_one(
        {"user_id": uid},
        {"$set": {"withdraw_mode": True}},
        upsert=True,
    )

    msg = await m.reply("📤 opening withdraw…")
    await progress_bar(msg, "withdraw")

    await msg.edit_text(
        f"🌑 withdraw panel\n{LINE}\n\n"
        f"⭐ balance: {u.get('stars', 0)}\n\n"
        "15 • 25 • 50 • 75 • 100 • 300 • 400\n\n"
        "✍️ send amount\n\n"
        f"🕒 {ts()}",
        reply_markup=home_reply_kb()
    )


# ───────────────────────────────────────────────
# support
# ───────────────────────────────────────────────
@app.on_message(filters.private & filters.regex("^📞"))
async def support(_, m):
    msg = await m.reply("📞 connecting support…")
    await shimmer(msg, "contacting team")

    await msg.edit_text(
        f"📞 support\n{LINE}\n\n"
        "@nexasupports\n\n"
        f"🕒 {ts()}",
        reply_markup=home_reply_kb()
    )


# ───────────────────────────────────────────────
# admin: add stars
# ───────────────────────────────────────────────
@app.on_message(filters.private & filters.command("addstars"))
async def admin_add(_, m):
    if m.from_user.id not in ADMIN_IDS:
        return

    try:
        _, uid, amount = m.text.split()
        uid, amount = int(uid), int(amount)
    except:
        return await m.reply("usage: /addstars user_id amount")

    users.update_one(
        {"user_id": uid},
        {"$inc": {"stars": amount}},
        upsert=True,
    )

    await m.reply(
        f"✨ stars added\n{LINE}\n"
        f"user id: {uid}\n"
        f"+{amount} ⭐\n\n"
        f"🕒 {ts()}"
    )


# ───────────────────────────────────────────────
# admin: deduct stars
# ───────────────────────────────────────────────
@app.on_message(filters.private & filters.command("deductstars"))
async def admin_deduct(_, m):
    if m.from_user.id not in ADMIN_IDS:
        return

    try:
        _, uid, amount = m.text.split()
        uid, amount = int(uid), int(amount)
    except:
        return await m.reply("usage: /deductstars user_id amount")

    u = users.find_one({"user_id": uid}) or {}
    if u.get("stars", 0) < amount:
        return await m.reply("❌ insufficient balance")

    users.update_one(
        {"user_id": uid},
        {"$inc": {"stars": -amount}},
    )

    await m.reply(
        f"⚠️ stars deducted\n{LINE}\n"
        f"user id: {uid}\n"
        f"-{amount} ⭐\n\n"
        f"🕒 {ts()}"
    )


# ───────────────────────────────────────────────
# text router (withdraw input)
# ───────────────────────────────────────────────
@app.on_message(filters.private & filters.text)
async def text_router(_, m):
    text = m.text.strip()
    uid = m.from_user.id

    if text.startswith("/") or text in MENU_BTNS:
        return

    u = users.find_one({"user_id": uid}) or {}
    if not u.get("withdraw_mode"):
        return

    users.update_one({"user_id": uid}, {"$set": {"withdraw_mode": False}})

    if withdraws.find_one({"user_id": uid, "status": "pending"}):
        return await m.reply("⏳ withdraw already pending")

    if not text.isdigit():
        return await m.reply("❌ enter valid amount")

amount = int(text)
    if amount not in ALLOWED_WITHDRAW:
        return await m.reply("⚠️ amount not allowed")

    if u.get("stars", 0) < amount:
        return await m.reply("❌ insufficient balance")

    users.update_one({"user_id": uid}, {"$inc": {"stars": -amount}})

    wd = withdraws.insert_one({
        "user_id": uid,
        "amount": amount,
        "status": "pending",
        "time": datetime.utcnow(),
    })

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("approve", callback_data=f"wd_approve_{wd.inserted_id}"),
        InlineKeyboardButton("reject", callback_data=f"wd_reject_{wd.inserted_id}"),
    ]])

    if ADMIN_LOG_GROUP:
        await safe_send(
            ADMIN_LOG_GROUP,
            f"📤 withdraw request\n{LINE}\n"
            f"user id: {uid}\n"
            f"amount: {amount} ⭐\n"
            f"status: pending\n"
            f"time: {ts()}",
            reply_markup=kb
        )

    await m.reply(
        f"✅ withdraw submitted\n{LINE}\n"
        f"amount: {amount} ⭐\n"
        f"status: pending\n\n"
        f"🕒 {ts()}",
        reply_markup=home_reply_kb()
    )


# ───────────────────────────────────────────────
# callback: approve / reject
# ───────────────────────────────────────────────
@app.on_callback_query(filters.regex("^wd_"))
async def withdraw_action(_, q):
    if q.from_user.id not in ADMIN_IDS:
        return await q.answer("not allowed", show_alert=True)

    _, action, wid = q.data.split("_")
    wid = ObjectId(wid)

    wd = withdraws.find_one({"_id": wid})
    if not wd or wd["status"] != "pending":
        return await q.answer("already processed", show_alert=True)

    uid = wd["user_id"]
    amount = wd["amount"]

    if action == "approve":
        withdraws.update_one(
            {"_id": wid},
            {"$set": {"status": "approved", "action_time": datetime.utcnow()}},
        )

        await safe_send(
            uid,
            f"✅ withdraw approved\n{LINE}\n"
            f"{amount} ⭐\n\n"
            f"🕒 {ts()}"
        )

        await q.message.edit_text("✅ approved")

    elif action == "reject":
        withdraws.update_one(
            {"_id": wid},
            {"$set": {"status": "rejected", "action_time": datetime.utcnow()}},
        )

        users.update_one({"user_id": uid}, {"$inc": {"stars": amount}})

        await safe_send(
            uid,
            f"❌ withdraw rejected\n{LINE}\n"
            f"refund: {amount} ⭐\n\n"
            f"🕒 {ts()}"
        )

        await q.message.edit_text("❌ rejected & refunded")


