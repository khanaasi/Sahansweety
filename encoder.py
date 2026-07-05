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

# Client type resolution bypass
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

# Custom font directory paths
os.makedirs("fonts", exist_ok=True)

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- DYNAMIC BLOCKS PROGRESS BARS ---
def make_progress_bar(percent):
    filled = int(percent / 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    return bar

async def prog(c, t, app, action):
    global last_time, start_time, status_msg_id
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    if now - last_time > 8 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_mb = speed / 1048576
        percent = (c / t) * 100 if t > 0 else 0
        bar = make_progress_bar(percent)
        
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip Task", callback_data="cancel_active_run")]])
        text = (
            f"⚡ **Task Action:** `{action}`\n"
            f"📊 `[{bar}] {percent:.2f}%`\n"
            f"📦 Size: `{c/1048576:.1f}MB / {t/1048576:.1f}MB`\n"
            f"⚡ Speed: `{speed_mb:.2f} MB/s`"
        )
        try:
            await app.edit_message_text(CHAT_ID, status_msg_id, text, reply_markup=cancel_markup)
        except:
            pass
        last_time = now

# --- DYNAMIC TELEGRAM LINK DOWNLOADER ---
async def download_tg_link(app, link, output_path=None):
    # Extracts group chat_id and message_id from 'https://t.me/c/chat_id/msg_id'
    parts = link.split("/")
    msg_id = int(parts[-1])
    try:
        msg = await app.get_messages(CHAT_ID, msg_id)
        if msg.document or msg.video or msg.photo:
            reset_prog()
            return await msg.download(
                file_name=output_path, 
                progress=prog, 
                progress_args=(app, f"Downloading {output_path or 'File'}")
            )
    except Exception as e:
        print(f"Failed download: {e}")
    return None

def get_font_name(font_path):
    try:
        font = TTFont(font_path)
        for record in font['name'].names:
            if record.nameID == 4:  # Full font name ID
                return record.toUnicode()
    except Exception as e:
        print(f"Error parsing font name: {e}")
    return "Arial"

def clean_dialogue(text):
    text = re.sub(r'\{[^}]+\}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

# --- TIMINGS UNALTERED SOFT EXTRACTION ---
def extract_clean_dialogue_ass(sub_path, out_ass_path):
    try:
        subs = pysubs2.load(sub_path, encoding="utf-8")
    except:
        subs = pysubs2.load(sub_path, encoding="latin-1")
    
    clean_subs = pysubs2.SSAFile()
    for line in subs:
        cleaned_text = clean_dialogue(line.text)
        if cleaned_text:
            clean_subs.append(pysubs2.SSAEvent(
                start=line.start, 
                end=line.end, 
                text=cleaned_text, 
                style="Default"
            ))
    clean_subs.save(out_ass_path)

def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except:
        return 0.0

# --- MAIN RUNNER EXECUTION ---
async def main():
    global status_msg_id
    app = Client("WorkflowWorker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    await app.start()

    init_msg = await app.send_message(
        CHAT_ID, 
        "⚙️ **Worker VM initialized.** Downloading media packages...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip Task", callback_data="cancel_active_run")]])
    )
    status_msg_id = init_msg.id

    try:
        # 1. Download Video
        video_file = await download_tg_link(app, VIDEO_ID, "video.mp4")
        if not video_file or not os.path.exists(video_file):
            raise Exception("Telegram side se video download fail ho gaya.")

        duration = get_video_duration(video_file)

        # 2. Download Font if active
        font_name = "Arial"
        if FONT_LINK != "none":
            # Direct HTTP file or link handling
            r = requests.get(FONT_LINK)
            if r.status_code == 200:
                font_path = "fonts/custom_font.ttf"
                with open(font_path, "wb") as f:
                    f.write(r.content)
                font_name = get_font_name(font_path)

        # 3. Process according to Task type
        if TASK_TYPE == "compress":
            # Extract internal soft subtitles if exist
            sub_extracted = "extracted_clean.ass"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-map", "0:s:0", "raw_sub.srt"], capture_output=True)
                if os.path.exists("raw_sub.srt") and os.path.getsize("raw_sub.srt") > 0:
                    extract_clean_dialogue_ass("raw_sub.srt", sub_extracted)
                else:
                    sub_extracted = None
            except:
                sub_extracted = None

            # Compression logic
            height = RESOLUTION.replace("p", "")
            out_name = f"compressed_{RESOLUTION}.mp4"
            
            await app.edit_message_text(CHAT_ID, status_msg_id, "⚙️ **Compressing Video...**", 
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip Task", callback_data="cancel_active_run")]]))
            
            cmd = [
                "ffmpeg", "-y", "-i", video_file, 
                "-vf", f"scale=-2:{height}", 
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", 
                "-c:a", "aac", "-b:a", "128k", out_name
            ]
            subprocess.run(cmd, check=True)

            # Deliver compressed items
            reset_prog()
            await app.send_document(USER_ID, document=out_name, caption=f"✅ Compressed Video ({RESOLUTION})",
                                    progress=prog, progress_args=(app, "Uploading Compressed Video to PM"))
            
            # Post to Desk Channel
            await app.send_document(-1003700822969, document=out_name, caption=f"🎬 Logs: Compressed Video ({RESOLUTION})")
            
            if sub_extracted and os.path.exists(sub_extracted):
                await app.send_document(USER_ID, document=sub_extracted, caption="📄 Extracted Dialogues ASS File")
                await app.send_document(-1003700822969, document=sub_extracted, caption="📄 Log: Extracted Dialogues ASS")

        elif TASK_TYPE == "hardsub":
            # Download Subtitle File
            sub_file = await download_tg_link(app, SUB_ID, "sub_raw")
            if not sub_file or not os.path.exists(sub_file):
                raise Exception("Subtitle file download failed.")

            # Load subtitle and set fixed standard properties
            try:
                subs = pysubs2.load(sub_file, encoding="utf-8")
            except:
                subs = pysubs2.load(sub_file, encoding="latin-1")

            is_ass = sub_file.lower().endswith('.ass')
            
            # Format and Style Customization
            if is_ass:
                # Check for embedded watermarks - do not alter size for ASS, keep styles intact
                has_watermark = any("watermark" in line.text.lower() for line in subs)
                # Apply custom font if available
                if FONT_LINK != "none":
                    for style_name, style_obj in subs.styles.items():
                        style_obj.fontname = font_name
            else:
                # Convert SRT/VTT to ASS and fix styles/size automatically
                new_subs = pysubs2.SSAFile()
                new_subs.styles["Default"] = pysubs2.SSAStyle(
                    fontname=font_name, fontsize=24, primarycolor=pysubs2.Color(255, 255, 255),
                    outlinecolor=pysubs2.Color(0, 0, 0), outline=2, shadow=1, marginl=20, marginr=20, marginv=15
                )
                for line in subs:
                    clean_txt = clean_dialogue(line.text)
                    new_subs.append(pysubs2.SSAEvent(start=line.start, end=line.end, text=clean_txt, style="Default"))
                subs = new_subs
                has_watermark = False

            subs.save("ready_sub.ass")

            # Download Watermark if requested
            wm_file = None
            if WM_ID != "none":
                # Handle watermark download
                wm_file = await download_tg_link(app, WM_ID, "watermark.png")

            # Finalize overlay & video filter strings
            vf_filter = "subtitles=ready_sub.ass"
            if FONT_LINK != "none":
                vf_filter = "subtitles=ready_sub.ass:fontsdir=fonts"

            # Overlay position mapping
            overlay_coord = "W-w-15:15" if WM_POS == "right" else "15:15"

            out_name = RENAME if RENAME != "none" else "hardsub_output.mp4"

            await app.edit_message_text(CHAT_ID, status_msg_id, "⚙️ **Hardsubbing and Encoding video...**", 
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip Task", callback_data="cancel_active_run")]]))

            if wm_file and os.path.exists(wm_file) and not has_watermark:
                cmd = [
                    "ffmpeg", "-y", "-i", video_file, "-i", wm_file, 
                    "-filter_complex", f"[0:v]{vf_filter}[vsub];[1:v]scale=200:-1[wm];[vsub][wm]overlay={overlay_coord}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", out_name
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-i", video_file, "-vf", vf_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", out_name
                ]

            subprocess.run(cmd, check=True)

            # Upload back to User's PM
            reset_prog()
            await app.send_document(USER_ID, document=out_name, caption=f"✅ Hardsubbed Complete: `{out_name}`",
                                    progress=prog, progress_args=(app, "Uploading Hardsub Video to PM"))
            
            # Post to log channel
            await app.send_document(-1003700822969, document=out_name, caption=f"🎬 Logs: Hardsubbed Video `{out_name}`")

        # Cleanup group messages
        await app.delete_messages(CHAT_ID, status_msg_id)

    except Exception as e:
        print(f"Error occurred: {e}")
        try:
            await app.edit_message_text(CHAT_ID, status_msg_id, f"❌ **Error occurred during process:** `{e}`")
        except:
            pass
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
