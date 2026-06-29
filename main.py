hereimport os, time, asyncio, threading, requests
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram.errors import FloodWait

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
REPO_NAME = os.getenv("REPO_NAME", "").strip()
PORT = 7860  # Hugging Face default port

OWNER_ID = 5351848105       
ALLOWED_USERS = [5344078567]             
ALLOWED_GROUPS = [-1003899919015] 

app = Client("AllInOneBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

users_data, UNAUTHORIZED_CAPTURED, BANNED_USERS = {}, set(), set()
BOT_BUSY = False
SLEEP_UNTIL = 0

task_queue = []

async def process_next_task():
    global BOT_BUSY
    if not task_queue:
        BOT_BUSY = False
        return
    
    BOT_BUSY = True
    task_func, args = task_queue.pop(0)
    try:
        await task_func(*args)
    except Exception as e:
        print(f"Error executing queued task: {e}")
    finally:
        await process_next_task()

async def add_to_queue(task_func, *args):
    task_queue.append((task_func, args))
    position = len(task_queue)
    if not BOT_BUSY:
        asyncio.create_task(process_next_task())
    return position

def is_authorized(m: Message):
    if not m.from_user: return False
    u_id = m.from_user.id    
    if u_id in BANNED_USERS: return False
    if u_id == OWNER_ID or u_id in ALLOWED_USERS or m.chat.id in ALLOWED_GROUPS: return True
    UNAUTHORIZED_CAPTURED.add(u_id)
    return False

def _send_to_github(workflow_name, task):
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{workflow_name}/dispatches"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    payload = {"ref": "main", "inputs": task}
    try:
        r = requests.post(url, headers=headers, json=payload)
        return (True, "Success") if r.status_code == 204 else (False, f"Code {r.status_code}: {r.text}")
    except Exception as e: 
        return False, str(e)

async def trigger_github(workflow_name, task): 
    return await asyncio.to_thread(_send_to_github, workflow_name, task)

@app.on_message(filters.command("start"))
async def start(c, m: Message):
    if not is_authorized(m) or time.time() < SLEEP_UNTIL: return
    text = "<b>🔥 All-in-One Subtitle Bot 🔥</b>\n\n<b>🎬 Encode/Hardsub:</b> /hsub, /extracttrack, /1080pdd, /720pdd, /480pdd\n<b>📝 AI Generate:</b> Reply to Video -> `/vtt`, `/srt`, `/ass`\n<b>🇮🇳 Gemini Translate:</b> Reply to Sub File -> `/hienglish`\n\n/cancel - Clear Active Task"
    await m.reply(text)

@app.on_message(filters.command(["cancel", "skip", "remm"]))
async def cancel_task(c, m: Message):
    global BOT_BUSY
    uid = m.from_user.id
    if uid in users_data: del users_data[uid]
    BOT_BUSY = False 
    if task_queue:
        task_queue.clear()
    await m.reply("🛑 Task memory and queue cleared. Bot is now FREE.")

# ================= QUEUED WORKFLOW TASKS =================
async def run_resize_task(target, media, m, st):
    try:
        success, err = await trigger_github("encode.yml", {
            "task_type": "resize", "video_id": media.file_id, "sub_id": "none", 
            "wm_id": "none", "wm_pos": "none", "rename": f"resized_{target}p.mp4", 
            "chat_id": str(m.chat.id), "resolution": target
        })
        await st.edit("✅ Sent to GitHub! Processing sequentially." if success else f"❌ Failed: {err}")
    except Exception as e:
        await st.edit(f"❌ Error during execution: {e}")

async def run_extract_task(media, m, st):
    try:
        success, err = await trigger_github("encode.yml", {
            "task_type": "extract", "video_id": media.file_id, "sub_id": "none", 
            "wm_id": "none", "wm_pos": "none", "rename": "extracted.srt", 
            "chat_id": str(m.chat.id), "resolution": "none"
        })
        await st.edit("✅ Extract Task Sent!" if success else f"❌ Failed: {err}")
    except Exception as e:
        await st.edit(f"❌ Error during execution: {e}")

async def run_hsub_task(task_payload, st):
    try:
        success, err = await trigger_github("encode.yml", task_payload)
        await st.edit("✅ Process started on GitHub!" if success else f"❌ Error: {err}")
    except Exception as e:
        await st.edit(f"❌ Error: {e}")

async def run_gen_task(task_payload, st):
    try:
        success, err = await trigger_github("generate.yml", task_payload)
        await st.edit(f"✅ AI Gen Task Sent!" if success else f"❌ Failed: {err}")
    except Exception as e:
        await st.edit(f"❌ Error: {e}")

# ================= ENCODE / HARDSUB / COMPRESS =================
@app.on_message(filters.command(["1080pdd", "720pdd", "480pdd"]))
async def resize_cmd(c, m: Message):
    if not is_authorized(m): return
    media = m.reply_to_message.video or m.reply_to_message.document if m.reply_to_message else None
    if not media: return await m.reply("❌ Reply to a video.")
    
    target = m.command[0].replace("pdd", "")
    st = await m.reply(f"⏳ Adding {target}p Compress task to queue...")
    
    pos = await add_to_queue(run_resize_task, target, media, m, st)
    if pos > 1:
        await st.edit(f"⏳ **Queued at Position #{pos}.** It will execute sequentially.")

@app.on_message(filters.command("extracttrack"))
async def extract_cmd(c, m: Message):
    if not is_authorized(m): return
    media = m.reply_to_message.video or m.reply_to_message.document if m.reply_to_message else None
    if not media: return await m.reply("❌ Reply to a video.")
    
    st = await m.reply("⏳ Adding Extract Track task to queue...")
    pos = await add_to_queue(run_extract_task, media, m, st)
    if pos > 1:
        await st.edit(f"⏳ **Queued at Position #{pos}.** It will execute sequentially.")

@app.on_message(filters.command("hsub"))
async def hsub_cmd(c, m: Message):
    if not is_authorized(m): return
    media = m.reply_to_message.video or m.reply_to_message.document if m.reply_to_message else None
    if not media: return await m.reply("❌ Reply to a video.")
    
    users_data[m.from_user.id] = {"type": "encode", "video_id": media.file_id, "chat_id": str(m.chat.id), "state": "WAIT_SUB", "file_name": media.file_name or "video.mp4"}
    await m.reply("📄 Send Subtitle File (.srt/.ass)", reply_to_message_id=m.id)

# ================= AI SUBTITLE / TRANSLATE =================
@app.on_message(filters.command(["vtt", "srt", "ass"]))
async def gen_sub(c, m: Message):
    if not is_authorized(m): return
    ftype = m.command[0].lower()
    media = m.reply_to_message.video or m.reply_to_message.document if m.reply_to_message else None
    if not media: return await m.reply("❌ Please reply to a video.")
    b_name = getattr(media, "file_name", "video.mp4").rsplit(".", 1)[0]
    
    if ftype == "ass":
        users_data[m.from_user.id] = {"type": "generate", "task_type": "extract_english", "file_id": media.file_id, "format_type": "ass", "chat_id": str(m.chat.id), "file_name": b_name, "custom_prompt": "none"}
        return await m.reply("❓ Kaunsa Style lagana hai?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 ASI Style + WM", callback_data="style_asi")], [InlineKeyboardButton("📄 Normal", callback_data="style_normal")]]))
    
    st = await m.reply("⏳ Adding AI Subtitle task to queue...")
    task_payload = {"task_type": "extract_english", "file_id": media.file_id, "format_type": ftype, "chat_id": str(m.chat.id), "msg_id": str(st.id), "file_name": b_name, "style_type": "normal", "custom_prompt": "none"}
    
    pos = await add_to_queue(run_gen_task, task_payload, st)
    if pos > 1:
        await st.edit(f"⏳ **Queued at Position #{pos}.** It will execute sequentially.")

@app.on_message(filters.command(["hienglish"]))
async def trans_sub(c, m: Message):
    if not is_authorized(m): return
    doc = m.reply_to_message.document if m.reply_to_message else None
    if not doc or not doc.file_name.endswith((".srt", ".vtt", ".ass")): return await m.reply("❌ Reply to a subtitle file.")
    b_name, ftype = doc.file_name.rsplit(".", 1)[0], doc.file_name.split('.')[-1]
    
    users_data[m.from_user.id] = {"type": "generate", "task_type": "translate_hinglish", "file_id": doc.file_id, "format_type": ftype, "chat_id": str(m.chat.id), "file_name": b_name, "state": "WAIT_PROMPT"}
    
    await m.reply("✍️ **Custom Prompt Dalo** (Dialogue flow / slang change karne ke liye).\n\nAgar purana normal translation chahiye toh 'Skip' dabao.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip (Normal Translate)", callback_data="prompt_skip")]]))

# ================= USER INPUT HANDLERS & ERROR CLEANUP =================
@app.on_message(filters.document | filters.photo | filters.text)
async def inputs(c, m: Message):
    uid = m.from_user.id
    if uid not in users_data: return
    d, state = users_data[uid], users_data[uid].get("state")
    
    if d.get("type") == "generate" and state == "WAIT_PROMPT":
        if m.text:
            d["custom_prompt"] = m.text
            if d["format_type"] == "ass":
                d["state"] = "WAIT_STYLE"
                await m.reply("❓ Kaunsa Style lagana hai?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 ASI Style + WM", callback_data="style_asi")], [InlineKeyboardButton("📄 Normal", callback_data="style_normal")]]))
            else:
                await send_gen_task(uid, m, "normal")
        else:
            await m.reply("❌ Invalid input. Flow Reset.")
            users_data.pop(uid, None)

    elif d.get("type") == "encode":
        if state == "WAIT_SUB":
            if m.document and m.document.file_name.endswith((".srt", ".ass")):
                d["sub_id"], d["state"] = m.document.file_id, "WAIT_WM_CHOICE"
                await m.reply("Add Watermark?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes", callback_data="wm_yes"), InlineKeyboardButton("No", callback_data="wm_skip")]]))
            else:
                await m.reply("❌ **Invalid file format!** Please send only `.srt` or `.ass` subtitle files. Task cancelled.")
                users_data.pop(uid, None)
                
        elif state == "WAIT_WM_PIC":
            if m.photo:
                d["wm_id"], d["state"] = m.photo.file_id, "WAIT_WM_POS"
                await m.reply("Watermark Position:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Top-Left", callback_data="pos_TL"), InlineKeyboardButton("Top-Right", callback_data="pos_TR")]]))
            else:
                await m.reply("❌ **Invalid input!** Photo expected. Task cancelled.")
                users_data.pop(uid, None)
                
        elif state == "WAIT_RENAME_TEXT" and m.text:
            d["file_name"] = m.text.strip() + ".mp4" if not m.text.endswith(".mp4") else m.text.strip()
            await send_hsub(uid, m)

@app.on_callback_query()
async def cbs(c, q: CallbackQuery):
    uid = q.from_user.id
    if uid not in users_data: return await q.answer("No active task!", show_alert=True)
    d, data = users_data[uid], q.data
    
    if data == "prompt_skip":
        d["custom_prompt"] = "none"
        if d["format_type"] == "ass":
            d["state"] = "WAIT_STYLE"
            await q.message.edit("❓ Kaunsa Style lagana hai?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 ASI Style + WM", callback_data="style_asi")], [InlineKeyboardButton("📄 Normal", callback_data="style_normal")]]))
        else:
            await send_gen_task(uid, q.message, "normal")
            
    elif data.startswith("style_"):
        style = "asi_style" if data == "style_asi" else "normal"
        await send_gen_task(uid, q.message, style)

    elif d.get("type") == "encode":
        if data == "wm_yes": 
            d["state"] = "WAIT_WM_PIC"
            await q.message.edit("🖼️ Send Photo for Watermark.")
        elif data in ["wm_skip", "pos_TL", "pos_TR"]:
            if data == "wm_skip": d["wm_id"] = d["wm_pos"] = "none"
            else: d["wm_pos"] = "TL" if data == "pos_TL" else "TR"
            d["state"] = "WAIT_RENAME_CHOICE"
            await q.message.edit("Rename file?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes", callback_data="rn_yes"), InlineKeyboardButton("Skip", callback_data="rn_skip")]]))
        elif data == "rn_yes": 
            d["state"] = "WAIT_RENAME_TEXT"
            await q.message.edit("📝 Send new file name.")
        elif data == "rn_skip": 
            await send_hsub(uid, q.message)

async def send_gen_task(uid, msg, style):
    d = users_data.pop(uid)
    st = await msg.reply("⏳ Queueing Translate Task...") if not isinstance(msg, Message) else await msg.edit("⏳ Queueing Translate Task...")
    
    task_payload = {
        "task_type": d["task_type"], "file_id": d["file_id"], "format_type": d["format_type"], 
        "chat_id": d["chat_id"], "msg_id": str(st.id if isinstance(msg, Message) else msg.id), 
        "file_name": d["file_name"], "style_type": style, "custom_prompt": d.get("custom_prompt", "none")
    }
    
    pos = await add_to_queue(run_gen_task, task_payload, st)
    if pos > 1:
        await st.edit(f"⏳ **Task queued at Position #{pos}.** It will start automatically.")

async def send_hsub(uid, msg):
    d = users_data.pop(uid)
    st = await msg.reply("⏳ Queueing Hardsub Task...")
    
    task_payload = {
        "task_type": "hsub", "video_id": d["video_id"], "sub_id": d.get("sub_id", "none"), 
        "wm_id": d.get("wm_id", "none"), "wm_pos": d.get("wm_pos", "none"), 
        "rename": d.get("file_name", "output.mp4"), "chat_id": d["chat_id"], "resolution": "none"
    }
    
    pos = await add_to_queue(run_hsub_task, task_payload, st)
    if pos > 1
