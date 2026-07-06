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

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- CUSTOM PROGRESS BAR STYLES ---
def get_download_bar(percent):
    total = 15
    filled = int(percent / 100 * total)
    return f"[{'>' * filled}{'-' * (total - filled)}]"

def get_process_bar(percent):
    total = 18
    filled = int(percent / 100 * total)
    seq = ["•", "°", ":", "°", "•", ":"]
    bar = "".join(seq[i % len(seq)] for i in range(filled))
    return f"[{bar}{'-' * (total - filled)}]"

def get_send_bar(percent):
    total = 10
    filled = int(percent / 100 * total)
    return f"[{'▓' * filled}{'░' * (total - filled)}]"

# --- HTTP UI UPDATER ---
def _sync_http_edit(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": CHAT_ID,
        "message_id": status_msg_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "🛑 Skip", "callback_data": "cancel_active_run"}]]}
    }
    try: requests.post(url, json=payload, timeout=5)
    except: pass

async def update_http_status(text):
    await asyncio.to_thread(_sync_http_edit, text)

# --- FAST 10-SECOND PYROGRAM PROGRESS BAR ---
async def prog(c, t, app_instance, step_name):
    global last_time, start_time, status_msg_id
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    if now - last_time > 10 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_mb = (speed / 1024) / 1024
        percent = (c / t) * 100 if t > 0 else 0
        
        if step_name == "hardsub_download" or step_name == "compress_download":
            bar = get_download_bar(percent)
            text = f"Downloading video\n{bar} [{percent:.0f}%]\n🚀 `{speed_mb:.2f} MB/s` | 📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`"
        else:
            bar = get_send_bar(percent)
            text = f"Sending video\n{bar} [{percent:.0f}%]\n🚀 `{speed_mb:.2f} MB/s` | 📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`"
            
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
        try: await app_instance.edit_message_text(CHAT_ID, status_msg_id, text, reply_markup=cancel_markup)
        except: pass
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
        res_dur = subprocess.run(cmd_dur, capture_output=True, text=True, timeout=10)
        if res_dur.stdout.strip(): duration = float(res_dur.stdout.strip())
    except: pass
    try:
        res_dim = subprocess.run(cmd_dim, capture_output=True, text=True, timeout=10)
        if res_dim.stdout.strip():
            parts = res_dim.stdout.strip().split(",")
            if len(parts) == 2: width, height = int(parts[0]), int(parts[1])
    except: pass
    return width, height, duration

async def download_tg_link(app_instance, link, output_path, step_name):
    msg_id = int(link.split("/")[-1])
    try:
        msg = await app_instance.get_messages(CHAT_ID, msg_id)
        if msg.document or msg.video or msg.photo:
            reset_prog()
            return await asyncio.wait_for(msg.download(file_name=output_path, progress=prog, progress_args=(app_instance, step_name)), timeout=1800)
    except Exception as e: 
        print(f"Download Error: {e}")
    return None

# --- STRICT DELIVERY MODULE (DOCUMENT FORMAT ONLY) ---
async def deliver_video_asset(app_instance, chat_id, target_user, file_path, caption, progress_callback):
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 100:
        raise Exception("Processed video is missing or empty!")

    thumb_path = "thumb.jpg"
    try: subprocess.run(["ffmpeg", "-y", "-i", file_path, "-ss", "00:00:01", "-vframes", "1", thumb_path], capture_output=True, timeout=15)
    except: pass
    if not os.path.exists(thumb_path): thumb_path = None

    desk_msg, file_id = None, None

    reset_prog()
    try:
        desk_msg = await asyncio.wait_for(
            app_instance.send_document(
                chat_id=DESK_CHANNEL_ID, document=file_path, caption=f"🎬 Logs: {caption}", thumb=thumb_path,
                progress=progress_callback, progress_args=(app_instance, "sending_video")
            ), timeout=1800
        )
        file_id = desk_msg.document.file_id
    except Exception as e:
        print(f"[DESK DOC UPLOAD ERROR] {e}")

    pm_msg = None
    try:
        if file_id:
            pm_msg = await app_instance.send_document(chat_id=target_user, document=file_id, caption=caption)
        else:
            reset_prog()
            pm_msg = await asyncio.wait_for(
                app_instance.send_document(
                    chat_id=target_user, document=file_path, caption=caption, thumb=thumb_path,
                    progress=progress_callback, progress_args=(app_instance, "sending_video")
                ), timeout=1800
            )
    except Exception as e_pm:
        print(f"[USER PM ERROR] {e_pm}")
        if not pm_msg:
            try: await app_instance.send_message(chat_id, text=f"⚠️ <a href='tg://user?id={target_user}'>User</a>, video Process ho chuki hai par PM me nahi bhej paaya! Bot ko private me Start karein.", parse_mode=ParseMode.HTML)
            except: pass

    return pm_msg or desk_msg

# --- MASTER RUNNER ---
async def main():
    global status_msg_id
    
    # MAX CONCURRENT TRANSMISSIONS ADDED = 10x DOWNLOADING SPEED!
    app = Client("worker_down", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, max_concurrent_transmissions=10)
    await app.start()

    if TRIGGER_MSG_ID and TRIGGER_MSG_ID != "none":
        try: await app.delete_messages(CHAT_ID, int(TRIGGER_MSG_ID))
        except: pass

    init_msg = await app.send_message(CHAT_ID, "⚙️ **Worker initialized.** Preparing fast downloads...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
    status_msg_id = init_msg.id

    try:
        step_dl = "hardsub_download" if TASK_TYPE == "hardsub" else "compress_download"
        video_file = await download_tg_link(app, VIDEO_ID, "video.mp4", step_dl)
        if not video_file or not os.path.exists(video_file) or os.path.getsize(video_file) < 1000:
            raise Exception("Telegram video download failed.")

        orig_width, orig_height, duration = get_video_dimensions_and_duration(video_file)

        font_name = "Arial"
        if FONT_LINK != "none":
            r = requests.get(FONT_LINK)
            if r.status_code == 200:
                font_path = "fonts/custom_font.ttf"
                with open(font_path, "wb") as f: f.write(r.content)
                font_name = get_font_name(font_path)
                
        sub_file = None
        wm_file = None
        has_watermark = False
        
        if TASK_TYPE == "hardsub":
            sub_file = await download_tg_link(app, SUB_ID, "sub_raw", "hardsub_download")
            if not sub_file or not os.path.exists(sub_file): raise Exception("Subtitle pipeline download failure.")

            try: subs = pysubs2.load(sub_file, encoding="utf-8")
            except: subs = pysubs2.load(sub_file, encoding="latin-1")

            is_ass = sub_file.lower().endswith('.ass')
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
            if WM_ID != "none" and not has_watermark:
                wm_file = await download_tg_link(app, WM_ID, "watermark.png", "hardsub_download")

        await app.stop()


        # ---------------- PHASE 2: PROCESSING ENCODE ----------------
        if TASK_TYPE == "compress":
            sub_extracted = "extracted_clean.ass"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-map", "0:s:0", "raw_sub.srt"], capture_output=True)
                if os.path.exists("raw_sub.srt") and os.path.getsize("raw_sub.srt") > 0: extract_clean_dialogues("raw_sub.srt", sub_extracted)
                else: sub_extracted = None
            except: sub_extracted = None

            reso_clean = str(RESOLUTION).replace("p", "").replace("P", "").strip() if RESOLUTION else ""
            if reso_clean and reso_clean.lower() != "none":
                scale_filter = f"scale=-2:{reso_clean}"
            else:
                scale_filter = "scale='trunc(iw/2)*2:trunc(ih/2)*2'"

            out_name = f"compressed_{reso_clean if reso_clean else 'output'}.mp4"
            await update_http_status(f"Compress/extract\n{get_process_bar(0)} [0.0%]")
            
            # MAGICAL FIX FOR SUBS: Added -map 0:v -map 0:a? -map 0:s? -c:s copy
            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-vf", scale_filter, 
                "-map", "0:v", "-map", "0:a?", "-map", "0:s?",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-threads", "0", 
                "-c:a", "aac", "-b:a", "128k", "-c:s", "copy", "-movflags", "+faststart", out_name
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_file]
            d_res = subprocess.run(dur_cmd, capture_output=True, text=True)
            duration = float(d_res.stdout.strip()) if d_res.stdout.strip() else 0.1

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
                                percent = min((int(line_str.split("=")[1]) / 1000000.0 / duration) * 100, 100.0)
                                asyncio.create_task(update_http_status(f"Compress/extract\n{get_process_bar(percent)} [{percent:.1f}%]"))
                            except: pass
                            last_edit = now
            await read_stdout()
            await process.wait()
            if process.returncode != 0: raise Exception("FFmpeg compression failed.")

        elif TASK_TYPE == "hardsub":
            vf_filter = "subtitles='ready_sub.ass':charenc=UTF-8"
            if FONT_LINK != "none": vf_filter += ":fontsdir=fonts"
            
            v_filter = f"scale='trunc(iw/2)*2:trunc(ih/2)*2',{vf_filter}"
            overlay_coord = "W-w-15:15" if WM_POS == "right" else "15:15"
            out_name = RENAME if RENAME != "none" else "hardsub_output.mp4"

            await update_http_status(f"Encoding + resizing\n{get_process_bar(0)} [0.0%]")

            if wm_file and os.path.exists(wm_file):
                cmd = [
                    "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-i", wm_file, 
                    "-filter_complex", f"[0:v]{v_filter}[vsub];[1:v]scale=200:-1[wm];[vsub][wm]overlay={overlay_coord}", 
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-threads", "0", 
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_name
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-vf", v_filter, 
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-threads", "0", 
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_name
                ]

            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            
            dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_file]
            d_res = subprocess.run(dur_cmd, capture_output=True, text=True)
            duration = float(d_res.stdout.strip()) if d_res.stdout.strip() else 0.1

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
                                percent = min((int(line_str.split("=")[1]) / 1000000.0 / duration) * 100, 100.0)
                                asyncio.create_task(update_http_status(f"Encoding + resizing\n{get_process_bar(percent)} [{percent:.1f}%]"))
                            except: pass
                            last_edit = now
            await read_stdout()
            await process.wait()
            if process.returncode != 0: raise Exception("FFmpeg hardsub encoding failed.")


        # ---------------- PHASE 3: UPLOAD ----------------
        app_up = Client("worker_up", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, max_concurrent_transmissions=10)
        await app_up.start()
        
        await update_http_status(f"Sending video\n{get_send_bar(0)} [0.0%]")
        
        if TASK_TYPE == "compress":
            await deliver_video_asset(app_up, CHAT_ID, USER_ID, out_name, f"✅ Complete 💯 Compression\n`{out_name}`", prog)
            
            if 'sub_extracted' in locals() and sub_extracted and os.path.exists(sub_extracted):
                try:
                    sub_desk = await asyncio.wait_for(app_up.send_document(DESK_CHANNEL_ID, document=sub_extracted, caption="📄 Log: Extracted Dialogues ASS"), timeout=600)
                    try: await app_up.send_document(USER_ID, document=sub_desk.document.file_id, caption="📄 Extracted Dialogues ASS File")
                    except: pass
                except: pass

        elif TASK_TYPE == "hardsub":
            await deliver_video_asset(app_up, CHAT_ID, USER_ID, out_name, f"✅ Complete 💯 Hardsub\n`{out_name}`", prog)

        try: await app_up.delete_messages(CHAT_ID, status_msg_id)
        except: pass
        await app_up.stop()

    except Exception as e:
        try: _sync_http_edit(f"❌ **Workflow Error:**\n<code>{html.escape(str(e))}</code>")
        except: pass

if __name__ == "__main__":
    asyncio.run(main())
