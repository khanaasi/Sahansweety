import os
import sys
import time
import asyncio
import re
import subprocess
import requests
import pyrogram.utils
import pysubs2
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fontTools.ttLib import TTFont

# Client peer resolver bypass
pyrogram.utils.get_peer_type = lambda p: "channel" if str(p).startswith("-100") else "chat" if str(p).startswith("-") else "user"

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

TASK_TYPE = os.getenv("TASK_TYPE")
VIDEO_ID = os.getenv("VIDEO_ID")  # Contains Telegram link format
SUB_ID = os.getenv("SUB_ID")
CHAT_ID = int(os.getenv("CHAT_ID"))
USER_ID = int(os.getenv("USER_ID"))
RESOLUTION = os.getenv("RESOLUTION")
WM_ID = os.getenv("WM_ID")
WM_POS = os.getenv("WM_POS")
RENAME = os.getenv("RENAME")
FONT_LINK = os.getenv("FONT_LINK")

last_time = 0
start_time = 0
status_msg_id = None

os.makedirs("fonts", exist_ok=True)

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- CUSTOM PROGRESS BAR BUILDERS (VERIFIED SCHEMES) ---

def get_hardsub_download_bar(percent):
    total_slots = 20
    filled = int(percent / 100 * total_slots)
    chars = ["•", "°"]
    bar_str = "".join(chars[i % 2] for i in range(filled)) + "-" * (total_slots - filled)
    return f"[{bar_str}] [{percent:.0f}%]"

def get_compress_download_bar(percent):
    total_slots = 18
    filled = int(percent / 100 * total_slots)
    bar_str = "►" * filled + "-" * (total_slots - filled)
    return f"[{bar_str}] {percent:.0f}%"

def get_hardsub_encode_bar(percent):
    total_slots = 10
    filled = int(percent / 100 * total_slots)
    bar_str = "▰" * filled + "▱" * (total_slots - filled)
    return f"[{bar_str}] {percent:.2f}%"

def get_compress_process_bar(percent):
    total_slots = 30
    filled = int(percent / 100 * total_slots)
    bar_str = "|" * filled + "." * (total_slots - filled)
    return f"[{bar_str}] {percent:.0f}%"

def get_send_bar(percent):
    total_slots = 12
    filled = int(percent / 100 * total_slots)
    bar_str = "█" * filled + "░" * (total_slots - filled)
    return f"[{bar_str}] {percent:.0f}%"

# --- PROGRESS DISPATCHER ---
async def prog(c, t, app, step_name):
    global last_time, start_time, status_msg_id
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    if now - last_time > 8 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_kb = speed / 1024
        percent = (c / t) * 100 if t > 0 else 0
        
        # Match progress layout dynamically
        if step_name == "hardsub_download":
            bar = get_hardsub_download_bar(percent)
            text = f"Downloading video\n{bar}\nSpeed: {speed_kb:.1f} kb/s"
        elif step_name == "compress_download":
            bar = get_compress_download_bar(percent)
            text = f"Downloading video\n{bar}\nSpeed: {speed_kb:.1f} kb/s"
        else:  # Sending video (Both)
            bar = get_send_bar(percent)
            text = f"Sending video\n{bar}\nSpeed: {speed_kb:.1f} kb/s"
            
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
        try:
            await app.edit_message_text(CHAT_ID, status_msg_id, text, reply_markup=cancel_markup)
        except:
            pass
        last_time = now

# --- TIMELINES UNALTERED DIALOGUE EXTRACER ---
def extract_clean_dialogues(input_subtitle, output_ass):
    try:
        subs = pysubs2.load(input_subtitle)
    except:
        subs = pysubs2.load(input_subtitle, encoding="latin-1")
        
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 640",
        "PlayResY: 360",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    def to_ass_time(ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        cs = (ms % 1000) // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
        
    for line in subs:
        # Clean text: remove styles, <>, or special codes
        text = line.text
        text = re.sub(r'\{[^}]+\}', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('\r', '').replace('\n', ' ')
        text = text.strip()
        
        if text:
            start_t = to_ass_time(line.start)
            end_t = to_ass_time(line.end)
            ass_lines.append(f"Dialogue: 0,{start_t},{end_t},Default,,0000,0000,0000,,{text}")
            
    with open(output_ass, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_lines))

# --- HELPERS ---
async def download_tg_link(app, link, output_path, step_name):
    parts = link.split("/")
    msg_id = int(parts[-1])
    try:
        msg = await app.get_messages(CHAT_ID, msg_id)
        if msg.document or msg.video or msg.photo:
            reset_prog()
            return await msg.download(
                file_name=output_path, 
                progress=prog, 
                progress_args=(app, step_name)
            )
    except Exception as e:
        print(f"Download error: {e}")
    return None

def get_font_name(font_path):
    try:
        font = TTFont(font_path)
        for record in font['name'].names:
            if record.nameID == 4:
                return record.toUnicode()
    except Exception as e:
        print(f"Font parsing error: {e}")
    return "Arial"

def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except:
        return 0.0

# --- MASTER RUNNER ---
async def main():
    global status_msg_id
    app = Client("WorkflowWorker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    await app.start()

    init_msg = await app.send_message(
        CHAT_ID, 
        "⚙️ **Worker initialized.** Pre-processing assets...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
    )
    status_msg_id = init_msg.id

    try:
        # 1. DOWNLOAD VIDEO
        step_dl = "hardsub_download" if TASK_TYPE == "hardsub" else "compress_download"
        video_file = await download_tg_link(app, VIDEO_ID, "video.mp4", step_dl)
        if not video_file or not os.path.exists(video_file):
            raise Exception("Telegram video payload retrieval failed.")

        duration = get_video_duration(video_file)

        # 2. AUTO-DELETE DOWNLOAD PROGRESS BAR
        try:
            await app.delete_messages(CHAT_ID, status_msg_id)
        except:
            pass

        # 3. DOWNLOAD FONT IF ACTIVE
        font_name = "Arial"
        if FONT_LINK != "none":
            r = requests.get(FONT_LINK)
            if r.status_code == 200:
                font_path = "fonts/custom_font.ttf"
                with open(font_path, "wb") as f:
                    f.write(r.content)
                font_name = get_font_name(font_path)

        # 4. START COMPRESSION WORKFLOW
        if TASK_TYPE == "compress":
            # Extract Timings-Unaltered Clean ASS Subtitle
            sub_extracted = "extracted_clean.ass"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-map", "0:s:0", "raw_sub.srt"], capture_output=True)
                if os.path.exists("raw_sub.srt") and os.path.getsize("raw_sub.srt") > 0:
                    extract_clean_dialogues("raw_sub.srt", sub_extracted)
                else:
                    sub_extracted = None
            except:
                sub_extracted = None

            height = RESOLUTION.replace("p", "")
            out_name = f"compressed_{RESOLUTION}.mp4"
            
            proc_msg = await app.send_message(
                CHAT_ID, 
                "Compress / extract\n" + get_compress_process_bar(0),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
            )
            status_msg_id = proc_msg.id

            # Compression with progress tracking
            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, 
                "-vf", f"scale=-2:{height}", 
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", 
                "-c:a", "aac", "-b:a", "128k", out_name
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if "out_time_us=" in line_str:
                    try:
                        us = int(line_str.split("=")[1])
                        percent = (us / 1000000.0 / duration) * 100
                        bar = get_compress_process_bar(percent)
                        await app.edit_message_text(CHAT_ID, status_msg_id, f"Compress / extract\n{bar}",
                                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
                    except:
                        pass
            await process.wait()

            # Clean processing block
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            # Direct Deliver Privately to PM
            upload_msg = await app.send_message(CHAT_ID, "Sending video\n" + get_send_bar(0))
            status_msg_id = upload_msg.id
            
            reset_prog()
            video_uploaded = await app.send_document(
                USER_ID, 
                document=out_name, 
                caption=f"✅ Complete 💯 Compression\n`{out_name}`",
                progress=prog, 
                progress_args=(app, "sending_video")
            )
            
            # Post to Log Channel
            await app.send_document(DESK_CHANNEL_ID, document=video_uploaded.document.file_id, caption=f"🎬 Logs: Compressed Video ({RESOLUTION})")
            
            if sub_extracted and os.path.exists(sub_extracted):
                sub_uploaded = await app.send_document(USER_ID, document=sub_extracted, caption="📄 Extracted Dialogues ASS File")
                await app.send_document(DESK_CHANNEL_ID, document=sub_uploaded.document.file_id, caption="📄 Log: Extracted Dialogues ASS")

        # 5. START HARDSUB WORKFLOW
        elif TASK_TYPE == "hardsub":
            sub_file = await download_tg_link(app, SUB_ID, "sub_raw", "hardsub_download")
            if not sub_file or not os.path.exists(sub_file):
                raise Exception("Subtitle pipeline download failure.")

            # Load subtitle configuration
            try:
                subs = pysubs2.load(sub_file, encoding="utf-8")
            except:
                subs = pysubs2.load(sub_file, encoding="latin-1")

            is_ass = sub_file.lower().endswith('.ass')
            has_watermark = False

            if is_ass:
                # Scan raw lines for embedded logs/watermarks (case-insensitive check)
                with open(sub_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if any(word in content for word in ["logo", "watermark", "cr", "credit"]):
                        has_watermark = True

                # Apply font selection if requested
                if FONT_LINK != "none":
                    for style_obj in subs.styles.values():
                        style_obj.fontname = font_name
            else:
                # SRT / VTT auto-scaling and sizing transformation
                new_subs = pysubs2.SSAFile()
                new_subs.styles["Default"] = pysubs2.SSAStyle(
                    fontname=font_name, fontsize=24, primarycolor=pysubs2.Color(255, 255, 255),
                    outlinecolor=pysubs2.Color(0, 0, 0), outline=2, shadow=1, marginl=20, marginr=20, marginv=15
                )
                for line in subs:
                    # Clean tags
                    clean_text = line.text
                    clean_text = re.sub(r'\{[^}]+\}', '', clean_text)
                    clean_text = re.sub(r'<[^>]+>', '', clean_text)
                    clean_text = clean_text.replace('\r', '').replace('\n', '\\N').strip()
                    if clean_text:
                        new_subs.append(pysubs2.SSAEvent(start=line.start, end=line.end, text=clean_text, style="Default"))
                subs = new_subs

            subs.save("ready_sub.ass")

            wm_file = None
            if WM_ID != "none" and not has_watermark:
                wm_file = await download_tg_link(app, WM_ID, "watermark.png", "hardsub_download")

            # Setup ffmpeg filter configuration
            vf_filter = "subtitles=ready_sub.ass"
            if FONT_LINK != "none":
                vf_filter = "subtitles=ready_sub.ass:fontsdir=fonts"

            overlay_coord = "W-w-15:15" if WM_POS == "right" else "15:15"
            out_name = RENAME if RENAME != "none" else "hardsub_output.mp4"

            proc_msg = await app.send_message(
                CHAT_ID, 
                "Encoding + resizing\n" + get_hardsub_encode_bar(0),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
            )
            status_msg_id = proc_msg.id

            if wm_file and os.path.exists(wm_file):
                cmd = [
                    "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-i", wm_file, 
                    "-filter_complex", f"[0:v]{vf_filter}[vsub];[1:v]scale=200:-1[wm];[vsub][wm]overlay={overlay_coord}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", out_name
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, "-vf", vf_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", out_name
                ]

            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if "out_time_us=" in line_str:
                    try:
                        us = int(line_str.split("=")[1])
                        percent = (us / 1000000.0 / duration) * 100
                        bar = get_hardsub_encode_bar(percent)
                        await app.edit_message_text(CHAT_ID, status_msg_id, f"Encoding + resizing\n{bar}",
                                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
                    except:
                        pass
            await process.wait()

            # Clean processing block
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            # Upload stage
            upload_msg = await app.send_message(CHAT_ID, "Sending video\n" + get_send_bar(0))
            status_msg_id = upload_msg.id

            reset_prog()
            video_uploaded = await app.send_document(
                USER_ID, 
                document=out_name, 
                caption=f"✅ Complete 💯 Hardsub\n`{out_name}`",
                progress=prog, 
                progress_args=(app, "sending_video")
            )
            
            # Logs desk channel post
            await app.send_document(DESK_CHANNEL_ID, document=video_uploaded.document.file_id, caption=f"🎬 Logs: Hardsubbed Video `{out_name}`")

        # Cleanup VM update frames
        await app.delete_messages(CHAT_ID, status_msg_id)

    except Exception as e:
        print(f"Workflow Exception: {e}")
        try:
            await app.send_message(CHAT_ID, f"❌ **Workflow Run Crash:** `{e}`")
        except:
            pass
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
