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
TRIGGER_MSG_ID = os.getenv("TRIGGER_MSG_ID")

last_time = 0
start_time = 0
status_msg_id = None

os.makedirs("fonts", exist_ok=True)

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- BALANCED HIGH-SPEED CLIENT CONFIGURATION ---
app = Client(
    "WorkflowWorker", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    workers=24,
    max_concurrent_transmissions=4
)

# --- PROGRESS BAR SCHEMES ---

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

# --- PROGRESS CALLBACK DISPATCHER ---
async def prog(c, t, app, step_name):
    global last_time, start_time, status_msg_id
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    if now - last_time > 6 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_kb = speed / 1024
        percent = (c / t) * 100 if t > 0 else 0
        
        # Adaptive speed units formatting
        if speed_kb >= 1024:
            speed_str = f"{speed_kb / 1024:.2f} MB/s"
        else:
            speed_str = f"{speed_kb:.1f} kb/s"
            
        if step_name == "hardsub_download":
            bar = get_hardsub_download_bar(percent)
            text = f"Downloading video\n{bar}\nSpeed: {speed_str}"
        elif step_name == "compress_download":
            bar = get_compress_download_bar(percent)
            text = f"Downloading video\n{bar}\nSpeed: {speed_str}"
        else:
            bar = get_send_bar(percent)
            text = f"Sending video\n{bar}\nSpeed: {speed_str}"
            
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
        
        # Launch message edits safely in background to avoid transmission block
        asyncio.create_task(edit_msg_safe(app, CHAT_ID, status_msg_id, text, cancel_markup))
        last_time = now

async def edit_msg_safe(app, chat_id, msg_id, text, markup):
    try:
        await app.edit_message_text(chat_id, msg_id, text, reply_markup=markup)
    except:
        pass

# --- TIMELINES UNALTERED CLEAN ASS EXTRACER ---
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

# --- DELIVERY MODULE (SAFE PRIVATE PM + FALLBACK GROUP DELIVERIES) ---
async def deliver_video_asset(app, chat_id, target_user, file_path, caption, progress, width=1920, height=1080, duration=0):
    """Attempts to deliver privately to User PM, falls back to group output on PM permission errors"""
    delivery_msg = None
    
    # Custom dimension parameters to completely bypass Pyrogram internal ffprobe locks
    try:
        reset_prog()
        delivery_msg = await asyncio.wait_for(
            app.send_video(
                chat_id=target_user,
                video=file_path,
                caption=caption,
                supports_streaming=True,
                width=width,
                height=height,
                duration=int(duration) if duration > 0 else None,
                progress=progress,
                progress_args=(app, "sending_video")
            ),
            timeout=900
        )
        return delivery_msg
    except Exception as e_pm_stream:
        print(f"[PM STREAM FAILURE] {e_pm_stream}")
        
    try:
        reset_prog()
        delivery_msg = await asyncio.wait_for(
            app.send_document(
                chat_id=target_user,
                document=file_path,
                caption=caption,
                progress=progress,
                progress_args=(app, "sending_video")
            ),
            timeout=900
        )
        return delivery_msg
    except Exception as e_pm_doc:
        print(f"[PM DOC FAILURE] {e_pm_doc}")

    # GROUP DELIVERY FALLBACK (If Bot is not started in PM)
    print("Initiating Group delivery fallback stream...")
    try:
        await app.send_message(
            chat_id=chat_id,
            text=f"⚠️ <a href='tg://user?id={target_user}'>User</a>, aapne bot ko PM me start nahi kiya hai, isliye video PM me nahi bheji ja saki!\n"
                 f"Maine processed video group me hi post kar di hai.",
            parse_mode="html"
        )
        reset_prog()
        delivery_msg = await asyncio.wait_for(
            app.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                supports_streaming=True,
                width=width,
                height=height,
                duration=int(duration) if duration > 0 else None,
                progress=progress,
                progress_args=(app, "sending_video")
            ),
            timeout=900
        )
        return delivery_msg
    except Exception as e_grp_stream:
        print(f"[GROUP STREAM FAILURE] {e_grp_stream}")

    try:
        reset_prog()
        delivery_msg = await asyncio.wait_for(
            app.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress,
                progress_args=(app, "sending_video")
            ),
            timeout=900
        )
        return delivery_msg
    except Exception as e_grp_doc:
        print(f"[CRITICAL DELIVERY FAILURE] All fallbacks failed: {e_grp_doc}")
        
    return None

# --- HELPERS ---
async def download_tg_link(app, link, output_path, step_name):
    parts = link.split("/")
    msg_id = int(parts[-1])
    try:
        msg = await app.get_messages(CHAT_ID, msg_id)
        if msg.document or msg.video or msg.photo:
            reset_prog()
            return await asyncio.wait_for(
                msg.download(
                    file_name=output_path, 
                    progress=prog, 
                    progress_args=(app, step_name)
                ),
                timeout=600
            )
    except asyncio.TimeoutError:
        raise Exception("Telegram file download stalled and timed out after 10 minutes.")
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

def get_video_dimensions_and_duration(video_path):
    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    cmd_dim = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path]
    
    duration = 0.0
    width, height = 1920, 1080
    
    try:
        res_dur = subprocess.run(cmd_dur, capture_output=True, text=True, check=True)
        duration = float(res_dur.stdout.strip())
    except:
        pass
        
    try:
        res_dim = subprocess.run(cmd_dim, capture_output=True, text=True, check=True)
        parts = res_dim.stdout.strip().split(",")
        width = int(parts[0])
        height = int(parts[1])
    except:
        pass
        
    return width, height, duration

# --- MASTER RUNNER ---
async def main():
    global status_msg_id
    await app.start()

    if TRIGGER_MSG_ID and TRIGGER_MSG_ID != "none":
        try:
            await app.delete_messages(CHAT_ID, int(TRIGGER_MSG_ID))
        except Exception as ex:
            print(f"Error purging trigger message: {ex}")

    init_msg = await app.send_message(
        CHAT_ID, 
        "⚙️ **Worker initialized.** Preparing high-speed downloads...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
    )
    status_msg_id = init_msg.id

    try:
        # 1. DOWNLOAD VIDEO (SUPER SPEED WITH TIMEOUT)
        step_dl = "hardsub_download" if TASK_TYPE == "hardsub" else "compress_download"
        video_file = await download_tg_link(app, VIDEO_ID, "video.mp4", step_dl)
        if not video_file or not os.path.exists(video_file) or os.path.getsize(video_file) < 1000:
            raise Exception("Telegram video download returned an empty file or failed completely.")

        # Probe dimensions and duration on the safe Python-Side
        orig_width, orig_height, duration = get_video_dimensions_and_duration(video_file)

        # Step 1 Complete -> Deleting Old Downloading Message
        try: await app.delete_messages(CHAT_ID, status_msg_id)
        except: pass

        # DOWNLOAD FONT IF ACTIVE
        font_name = "Arial"
        if FONT_LINK != "none":
            r = requests.get(FONT_LINK)
            if r.status_code == 200:
                font_path = "fonts/custom_font.ttf"
                with open(font_path, "wb") as f:
                    f.write(r.content)
                font_name = get_font_name(font_path)

        # 2. START COMPRESSION WORKFLOW
        if TASK_TYPE == "compress":
            sub_extracted = "extracted_clean.ass"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-map", "0:s:0", "raw_sub.srt"], capture_output=True)
                if os.path.exists("raw_sub.srt") and os.path.getsize("raw_sub.srt") > 0:
                    extract_clean_dialogues("raw_sub.srt", sub_extracted)
                else:
                    sub_extracted = None
            except:
                sub_extracted = None

            height_target = int(RESOLUTION.replace("p", "").replace("P", ""))
            out_name = f"compressed_{RESOLUTION.lower()}.mp4"
            
            proc_msg = await app.send_message(
                CHAT_ID, 
                "Compress / extract\n" + get_compress_process_bar(0),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
            )
            status_msg_id = proc_msg.id

            # Safe python-side height verification to prevent upscale crashes and odd aspect ratios
            final_height = min(orig_height, height_target)
            scale_filter = f"scale=-2:{final_height}"
            
            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1", "-i", video_file, 
                "-vf", scale_filter, 
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", 
                "-c:a", "aac", "-b:a", "128k", out_name
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT
            )
            
            output_lines = []
            
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line: break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    output_lines.append(line_str)
                    if "out_time_us=" in line_str:
                        try:
                            us = int(line_str.split("=")[1])
                            percent = (us / 1000000.0 / duration) * 100
                            bar = get_compress_process_bar(percent)
                            await app.edit_message_text(
                                CHAT_ID, status_msg_id, 
                                f"Compress / extract\n{bar}",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]]))
                        except:
                            pass
                            
            await read_stdout()
            await process.wait()

            if process.returncode != 0:
                err_msg = "\n".join(output_lines[-15:])
                raise Exception(f"FFmpeg compression failed: {err_msg}")

            # Step 2 Complete -> Deleting Old Processing Message
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            # 3. UPLOADING PROGRESS STAGE (SUPER SPEED)
            upload_msg = await app.send_message(
                CHAT_ID, 
                "Sending video\n" + get_send_bar(0),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
            )
            status_msg_id = upload_msg.id
            
            # Predict compressed dimensions safely
            aspect_ratio = orig_width / orig_height if orig_height > 0 else 16/9
            final_width = int(round(final_height * aspect_ratio / 2) * 2)

            # Safe Private PM + Fallback delivery with keyword corrected parameters
            video_uploaded = await deliver_video_asset(
                app=app,
                chat_id=CHAT_ID,
                target_user=USER_ID,
                file_path=out_name,
                caption=f"✅ Complete 💯 Compression\n{os.path.basename(out_name)}",
                progress=prog, # Consistent verified parameter
                width=final_width,
                height=final_height,
                duration=duration
            )
            
            # Post final outputs to Logs/Desk Channel
            if video_uploaded:
                try:
                    await app.send_document(
                        DESK_CHANNEL_ID, 
                        document=video_uploaded.video.file_id if video_uploaded.video else video_uploaded.document.file_id, 
                        caption=f"🎬 Logs: Compressed Video ({RESOLUTION})"
                    )
                except Exception as log_err:
                    print(f"[LOG CHANNEL ERROR] {log_err}")
            
            if sub_extracted and os.path.exists(sub_extracted):
                try:
                    sub_uploaded = await app.send_document(USER_ID, document=sub_extracted, caption="📄 Extracted Dialogues ASS File")
                    await app.send_document(DESK_CHANNEL_ID, document=sub_uploaded.document.file_id, caption="📄 Log: Extracted Dialogues ASS")
                except Exception as sub_err:
                    print(f"[SUB ERROR] {sub_err}")

        # 4. START HARDSUB WORKFLOW
        elif TASK_TYPE == "hardsub":
            sub_file = await download_tg_link(app, SUB_ID, "sub_raw", "hardsub_download")
            if not sub_file or not os.path.exists(sub_file):
                raise Exception("Subtitle pipeline download failure.")

            try:
                subs = pysubs2.load(sub_file, encoding="utf-8")
            except:
                subs = pysubs2.load(sub_file, encoding="latin-1")

            is_ass = sub_file.lower().endswith('.ass')
            has_watermark = False

            if is_ass:
                with open(sub_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if any(word in content for word in ["logo", "watermark", "cr", "credit"]):
                        has_watermark = True

                if FONT_LINK != "none":
                    for style_obj in subs.styles.values():
                        style_obj.fontname = font_name
            else:
                new_subs = pysubs2.SSAFile()
                new_subs.styles["Default"] = pysubs2.SSAStyle(
                    fontname=font_name, fontsize=24, primarycolor=pysubs2.Color(255, 255, 255),
                    outlinecolor=pysubs2.Color(0, 0, 0), outline=2, shadow=1, marginl=20, marginr=20, marginv=15
                )
                for line in subs:
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

            vf_filter = "subtitles=ready_sub.ass"
            if FONT_LINK != "none":
                vf_filter = "subtitles=ready_sub.ass:fontsdir=fonts"

            overlay_coord = "W-w-15:15" if WM_POS == "right" else "15:15"
            out_name = RENAME if RENAME != "none" else "hardsub_output.mp4"

            # Step 1 Complete -> Purging Old Progress Message
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

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

            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT
            )
            
            output_lines = []
            
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line: break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    output_lines.append(line_str)
                    if "out_time_us=" in line_str:
                        try:
                            us = int(line_str.split("=")[1])
                            percent = (us / 1000000.0 / duration) * 100
                            bar = get_hardsub_encode_bar(percent)
                            await app.edit_message_text(
                                CHAT_ID, status_msg_id, 
                                f"Encoding + resizing\n{bar}",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
                            )
                        except:
                            pass
            await read_stdout()
            await process.wait()

            if process.returncode != 0:
                err_msg = "\n".join(output_lines[-15:])
                raise Exception(f"FFmpeg hardsub encoding failed: {err_msg}")

            # Step 2 Complete -> Purging Old Progress Message
            try: await app.delete_messages(CHAT_ID, status_msg_id)
            except: pass

            # 3. UPLOADING PROGRESS STAGE (SUPER SPEED)
            upload_msg = await app.send_message(
                CHAT_ID, 
                "Sending video\n" + get_send_bar(0),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Skip", callback_data="cancel_active_run")]])
            )
            status_msg_id = upload_msg.id

            out_width, out_height, out_duration = get_video_dimensions_and_duration(out_name)

            video_uploaded = await deliver_video_asset(
                app=app,
                chat_id=CHAT_ID,
                target_user=USER_ID,
                file_path=out_name,
                caption=f"✅ Complete 💯 Hardsub\n{os.path.basename(out_name)}",
                progress=prog, # Consistent verified parameter
                width=out_width,
                height=out_height,
                duration=out_duration
            )
            
            if video_uploaded:
                try:
                    await app.send_document(
                        DESK_CHANNEL_ID, 
                        document=video_uploaded.video.file_id if video_uploaded.video else video_uploaded.document.file_id, 
                        caption=f"🎬 Logs: Hardsubbed Video `{out_name}`"
                    )
                except Exception as log_err:
                    print(f"[LOG CHANNEL ERROR] {log_err}")

        # Step 3 Complete -> Final Cleanup of Upload progress message
        try: await app.delete_messages(CHAT_ID, status_msg_id)
        except: pass

    except Exception as e:
        print(f"Workflow Exception: {e}")
        # ALWAYS PURGE THE CURRENT STUCK PROGRESS MESSAGE DURING CRASH
        if status_msg_id:
            try:
                await app.delete_messages(CHAT_ID, status_msg_id)
            except:
                pass
        try:
            # Safe HTML Escaping for Pyrogram's Telegram delivery
            error_clean = html.escape(str(e))
            await app.send_message(CHAT_ID, f"❌ **Workflow Run Crash:**\n<code>{error_clean}</code>", parse_mode="html")
        except:
            pass
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
