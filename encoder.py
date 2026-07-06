import os
import sys
import time
import asyncio
import re
import subprocess
import requests
import pyrogram.utils
import pyrogram
import pysubs2
import html
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from fontTools.ttLib import TTFont

# Client peer resolver bypass
pyrogram.utils.get_peer_type = lambda p: "channel" if str(p).startswith("-100") else "chat" if str(p).startswith("-") else "user"

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

TASK_TYPE = os.getenv("TASK_TYPE")
VIDEO_ID = os.getenv("VIDEO_ID")
SUB_ID = os.getenv("SUB_ID")
CHAT_ID = int(os.getenv("CHAT_ID"))
USER_ID = int(os.getenv("USER_ID"))
RESOLUTION = os.getenv("RESOLUTION")
WM_ID = os.getenv("WM_ID")
WM_POS = os.getenv("WM_POS")
RENAME = os.getenv("RENAME")
FONT_LINK = os.getenv("FONT_LINK")
TRIGGER_MSG_ID = os.getenv("TRIGGER_MSG_ID")

DESK_CHANNEL_ID = -1003700822969

last_time = 0
start_time = 0
status_msg_id = None

os.makedirs("fonts", exist_ok=True)

app = Client("WorkflowWorker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- NEW 10-SECOND PROGRESS ENGINE (From your encoder.py to FIX 0% HANG) ---
async def prog(c, t, app, step_name):
    global last_time, start_time, status_msg_id
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    # EXACT FIX: 10 Second interval stops Telegram from dropping the upload connection!
    if now - last_time > 10 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_mb = (speed / 1024) / 1024
        percent = (c / t) * 100 if t > 0 else 0
        
        if step_name == "hardsub_download" or step_name == "compress_download":
            text = f"📥 Downloading Video...\n⏳ `[{percent:.1f}%]`\n🚀 Speed: `{speed_mb:.2f} MB/s`\n📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`"
        else:
            text = f"📤 Sending Video...\n⏳ `[{percent:.1f}%]`\n🚀 Speed: `{speed_mb:.2f} MB/s`\n📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`"
            
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
        
        try:
            await app.edit_message_text(CHAT_ID, status_msg_id, text, reply_markup=cancel_markup)
        except:
            pass
        last_time = now

# --- TIMELINES UNALTERED CLEAN ASS EXTRACER ---
def extract_clean_dialogues(input_subtitle, output_ass):
    try: subs = pysubs2.load(input_subtitle)
    except: subs = pysubs2.load(input_subtitle, encoding="latin-1")
        
    ass_lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 640", "PlayResY: 360", "",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    def to_ass_time(ms):
        h, m, s, cs = ms // 3600000, (ms % 3600000) // 60000, (ms % 60000) // 1000, (ms % 1000) // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
        
    for line in subs:
        text = re.sub(r'<[^>]+>', '', re.sub(r'\{[^}]+\}', '', line.text)).replace('\r', '').replace('\n', ' ').strip()
        if text: ass_lines.append(f"Dialogue: 0,{to_ass_time(line.start)},{to_ass_time(line.end)},Default,,0000,0000,0000,,{text}")
    with open(output_ass, "w", encoding="utf-8") as f: f.write("\n".join(ass_lines))

def get_font_name(font_path):
    try:
        font = TTFont(font_path)
        for record in font['name'].names:
            if record.nameID == 4: return record.toUnicode()
    except: pass
    return "Arial"

def get_video_dimensions_and_duration(video_path):
    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    cmd_dim = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path]
    width, height, duration = 1280, 720, 0.0
    try:
        res_dur = subprocess.run(cmd_dur, capture_output=True, text=True, check=True)
        if res_dur.stdout.strip(): duration = float(res_dur.stdout.strip())
    except: pass
    try:
        res_dim = subprocess.run(cmd_dim, capture_output=True, text=True, check=True)
        if res_dim.stdout.strip():
            parts = res_dim.stdout.strip().split(",")
            if len(parts) == 2: width, height = int(parts[0]), int(parts[1])
    except: pass
    return width, height, duration

async def download_tg_link(app, link, output_path, step_name):
    msg_id = int(link.split("/")[-1])
    try:
        msg = await app.get_messages(CHAT_ID, msg_id)
        if msg.document or msg.video or msg.photo:
            reset_prog()
            return await asyncio.wait_for(msg.download(file_name=output_path, progress=prog, progress_args=(app, step_name)), timeout=600)
    except: pass
    return None

# --- STRICT DELIVERY MODULE ---
async def deliver_video_asset(app, chat_id, target_user, file_path, caption, progress_callback):
    """
    1. Desk channel pe bhejega
    2. Wahi file instantly User ke PM me bhejega
    3. Group me kuch upload nahi hoga (No Fallback Video in Group)
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 100:
        raise Exception("Processed video is missing or empty!")

    width, height, duration = get_video_dimensions_and_duration(file_path)

    desk_msg, file_id, is_video = None, None, True

    # Upload directly to Desk Channel First
    reset_prog()
    try:
        desk_msg = await app.send_video(
            chat_id=DESK_CHANNEL_ID,
            video=file_path,
            caption=f"🎬 Logs: {caption}",
            duration=int(duration), 
            width=width,            
            height=height,          
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(app, "sending_video")
        )
        file_id = desk_msg.video.file_id if desk_msg.video else desk_msg.document.file_id
        is_video = bool(desk_msg.video)
    except Exception as e:
        print(f"[DESK UPLOAD ERROR] {e}")

    # Forward to User PM
    pm_msg = None
    try:
        if file_id:
            # FAST 0-Second Delivery via Cache
            if is_video: pm_msg = await app.send_video(chat_id=target_user, video=file_id, caption=caption)
            else: pm_msg = await app.send_document(chat_id=target_user, document=file_id, caption=caption)
        else:
            # Manual direct upload if Desk fails
            reset_prog()
            pm_msg = await app.send_video(
                chat_id=target_user,
                video=file_path,
                caption=caption,
                duration=int(duration),
                width=width,
                height=height,
                supports_streaming=True,
                progress=progress_callback,
                progress_args=(app, "sending_video")
            )
    except Exception as e_pm:
        print(f"[USER PM ERROR] {e_pm}")
        try:
            await app.send_message(
                chat_id=chat_id,
                text=f"⚠️ <a href='tg://user?id={target_user}'>User</a>, aapki video processed ho chuki hai par mai ise aapke PM me bhej nahi saka kyunki aapne mujhe PM me start nahi kiya hai!\n\n👉 Kripya private me `/start` karein.",
                parse_mode=ParseMode.HTML
            )
        except: pass

    return pm_msg or desk_msg

# --- MASTER RUNNER ---
async def main():
    global status_msg_id
    await app.start()

    if TRIGGER_MSG_ID and TRIGGER_MSG_ID != "none":
        try: await app.delete_messages(CHAT_ID, int(TRIGGER_MSG_ID))
        except: pass

    init_msg = await app.send_message(
        CHAT_ID, 
        "⚙️ **Worker initialized.** Preparing fast downloads...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
    )
    status_msg_id = init_msg.id

    try:
        step_dl = "hardsub_download" if TASK_TYPE == "hardsub" else "compress_download"
        video_file = await download_tg_link(app, VIDEO_ID, "video.mp4", step_dl)
        if not video_file or not os.path.exists(video_file) or os.path.getsize(video_file) < 1000:
            raise Exception("Telegram video download failed.")

        orig_width, orig_height, duration = get_video_dimensions_and_duration(video_file)

        try: await app.delete_messages(CHAT_ID, status_msg_id)
        except: pass

        font_name = "Arial"
        if FONT_LINK != "none":
            r = requests.get(FONT_LINK)
            if r.status_code == 200:
                font_path = "fonts/custom_font.ttf"
                with open(font_path, "wb") as f: f.write(r.content)
                font_name = get_font_name(font_path)

        # ==================== COMPRESS / EXTRACT WORKFLOW ====================
        if TASK_TYPE == "compress":
            sub_extracted = "extracted_clean.ass"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-map", "0:s:0", "-c:s", "copy", "raw_sub.srt"], capture_output=True)
                if os.path.exists("raw_sub.srt") and os.path.getsize("raw_sub.srt") > 0: extract_clean_dialogues("raw_sub.srt", sub_extracted)
                else: sub_extracted = None
            except: sub_extracted = None

            height_target = int(RESOLUTION.replace("p", "").replace("P", ""))
            out_name = f"compressed_{RESOLUTION.lower()}.mp4"
            
            proc_msg = await app.send_message(CHAT_ID, "⚙️ Compress / extract\n⏳ `[0.0%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
            status_msg_id = proc_msg.id

            final_height = min(orig_height, height_target)
            scale_filter = f"scale=-2:{final_height}"
            
            # SPEED HACKS INJECTED: -threads 0 uses max github cores, -preset ultrafast
            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, 
                "-vf", scale_filter, 
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-threads", "0", 
                "-c:a", "aac", "-b:a", "128k", 
                "-movflags", "+faststart", out_name
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            last_edit = time.time()
            async def read_stdout():
                nonlocal last_edit
                while True:
                    line = await process.stdout.readline()
                    if not line: break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if "out_time_us=" in line_str:
                        now = time.time()
                        if now - last_edit > 10:
                            try:
                                percent = (int(line_str.split("=")[1]) / 1000000.0 / duration) * 100
                                await app.edit_message_text(CHAT_ID, status_msg_id, f"⚙️ Compress / extract\n⏳ `[{percent:.1f}%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
                            except: pass
                            last_edit = now
                            
            await read_stdout()
            await process.wait()

            if process.returncode != 0: raise Exception("FFmpeg compression failed.")

            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            upload_msg = await app.send_message(CHAT_ID, "📤 Sending video\n⏳ `[0.0%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
            status_msg_id = upload_msg.id
            
            await deliver_video_asset(app, CHAT_ID, USER_ID, out_name, f"✅ Complete 💯 Compression\n`{out_name}`", prog)
            
            if sub_extracted and os.path.exists(sub_extracted):
                try:
                    sub_desk = await app.send_document(DESK_CHANNEL_ID, document=sub_extracted, caption="📄 Log: Extracted Dialogues ASS")
                    try: await app.send_document(USER_ID, document=sub_desk.document.file_id, caption="📄 Extracted Dialogues ASS File")
                    except: pass
                except: pass

        # ==================== HARDSUB WORKFLOW ====================
        elif TASK_TYPE == "hardsub":
            sub_file = await download_tg_link(app, SUB_ID, "sub_raw", "hardsub_download")
            if not sub_file or not os.path.exists(sub_file): raise Exception("Subtitle pipeline download failure.")

            try: subs = pysubs2.load(sub_file, encoding="utf-8")
            except: subs = pysubs2.load(sub_file, encoding="latin-1")

            is_ass, has_watermark = sub_file.lower().endswith('.ass'), False
            if is_ass:
                with open(sub_file, 'r', encoding='utf-8', errors='ignore') as f:
                    if any(word in f.read().lower() for word in ["logo", "watermark", "cr", "credit"]): has_watermark = True
                if FONT_LINK != "none":
                    for style_obj in subs.styles.values(): style_obj.fontname = font_name
            else:
                new_subs = pysubs2.SSAFile()
                new_subs.styles["Default"] = pysubs2.SSAStyle(fontname=font_name, fontsize=24, primarycolor=pysubs2.Color(255, 255, 255), outlinecolor=pysubs2.Color(0, 0, 0), outline=2, shadow=1, marginl=20, marginr=20, marginv=15)
                for line in subs:
                    clean_text = re.sub(r'<[^>]+>', '', re.sub(r'\{[^}]+\}', '', line.text)).replace('\r', '').replace('\n', '\\N').strip()
                    if clean_text: new_subs.append(pysubs2.SSAEvent(start=line.start, end=line.end, text=clean_text, style="Default"))
                subs = new_subs

            subs.save("ready_sub.ass")
            wm_file = await download_tg_link(app, WM_ID, "watermark.png", "hardsub_download") if (WM_ID != "none" and not has_watermark) else None
            vf_filter = "subtitles=ready_sub.ass:fontsdir=fonts" if FONT_LINK != "none" else "subtitles=ready_sub.ass"
            overlay_coord = "W-w-15:15" if WM_POS == "right" else "15:15"
            out_name = RENAME if RENAME != "none" else "hardsub_output.mp4"

            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            proc_msg = await app.send_message(CHAT_ID, "⚙️ Encoding + resizing\n⏳ `[0.0%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
            status_msg_id = proc_msg.id

            # SPEED HACKS INJECTED: Max Threads, ultrafast preset
            if wm_file and os.path.exists(wm_file):
                cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-i", wm_file, "-filter_complex", f"[0:v]{vf_filter}[vsub];[1:v]scale=200:-1[wm];[vsub][wm]overlay={overlay_coord}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-threads", "0", "-c:a", "aac", "-movflags", "+faststart", out_name]
            else:
                cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-vf", vf_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-threads", "0", "-c:a", "aac", "-movflags", "+faststart", out_name]

            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            last_edit = time.time()
            async def read_stdout():
                nonlocal last_edit
                while True:
                    line = await process.stdout.readline()
                    if not line: break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if "out_time_us=" in line_str:
                        now = time.time()
                        if now - last_edit > 10:
                            try:
                                percent = (int(line_str.split("=")[1]) / 1000000.0 / duration) * 100
                                await app.edit_message_text(CHAT_ID, status_msg_id, f"⚙️ Encoding + resizing\n⏳ `[{percent:.1f}%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
                            except: pass
                            last_edit = now
            await read_stdout()
            await process.wait()

            if process.returncode != 0: raise Exception("FFmpeg hardsub encoding failed.")

            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            upload_msg = await app.send_message(CHAT_ID, "📤 Sending video\n⏳ `[0.0%]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
            status_msg_id = upload_msg.id

            await deliver_video_asset(app, CHAT_ID, USER_ID, out_name, f"✅ Complete 💯 Hardsub\n`{out_name}`", prog)

        try: await app.delete_messages(CHAT_ID, status_msg_id)
        except: pass

    except Exception as e:
        if status_msg_id:
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass
        try: await app.send_message(CHAT_ID, f"❌ **Workflow Error:**\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        except: pass
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
