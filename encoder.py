import os, sys, time, asyncio, re, subprocess, pyrogram.utils, pysubs2, html
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Pyrogram ID compatibility patch
pyrogram.utils.get_peer_type = lambda p: "channel" if str(p).startswith("-100") else "chat" if str(p).startswith("-") else "user"

# --- ENV VARIABLES ---
API_ID, API_HASH, BOT_TOKEN = int(os.getenv("API_ID")), os.getenv("API_HASH"), os.getenv("BOT_TOKEN")
TASK_TYPE, VIDEO_ID, SUB_ID = os.getenv("TASK_TYPE"), os.getenv("VIDEO_ID"), os.getenv("SUB_ID")
CHAT_ID, RESO, WM_ID = int(os.getenv("CHAT_ID")), os.getenv("RESOLUTION"), os.getenv("WM_ID")
WM_POS, RENAME = os.getenv("WM_POS"), os.getenv("RENAME")

last_time = 0
start_time = 0
first_edit = True
status_msg_id = None  # Global status message tracker for fail-proof editing

def reset_prog():
    global last_time, start_time, first_edit
    last_time = time.time()
    start_time = time.time()
    first_edit = True

# --- CANCEL KEYBOARD HELPER ---
def get_cancel_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel Task", callback_data="cancel_action_run")]])

# --- UNIQUE PROGRESS BAR GENERATOR ---
def get_progress_bar(percentage, style="block"):
    percentage = max(0.0, min(100.0, percentage))
    total_steps = 15
    filled = int(round((percentage / 100.0) * total_steps))
    
    if style == "block":
        return "▰" * filled + "▱" * (total_steps - filled)
        
    elif style == "dot":
        filled_str = "".join("°" if i % 2 == 0 else "•" for i in range(filled))
        empty_str = "-" * (total_steps - filled)
        return filled_str + empty_str
        
    elif style == "heartbeat":
        frames = [
            "\u200e❤️‍🔥\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200e❤️‍🔥\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩ\u200e❤️‍🔥\u200e٨ـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ\u200e❤️‍🔥\u200eـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨\u200e❤️‍🔥\u200eـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ\u200e❤️‍🔥\u200e٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨\u200e❤️‍🔥\u200eـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ\u200e❤️‍🔥\u200eﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩﮩ\u200e❤️‍🔥\u200eـ\u200eﮩ٨ـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ\u200e❤️‍🔥\u200eـ\u200eﮩ٨ـ", 
            "ﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩﮩ٨ـ\u200eﮩ٨ـ\u200eﮩ\u200e❤️‍🔥\u200e", 
        ]
        idx = int(percentage / 10)
        idx = max(0, min(10, idx))
        return frames[idx]
        
    return "■" * filled + "□" * (total_steps - filled)

# --- PROGRESS DISPATCHER ---
async def prog(c, t, app, mid, action):
    global last_time, start_time, first_edit
    try:
        now = time.time()
        if start_time == 0:
            start_time = now
            last_time = now
            return
            
        if first_edit or now - last_time > 10 or c == t:
            first_edit = False
            last_time = now
            elapsed = now - start_time
            speed = c / elapsed if elapsed > 0 else 0
            speed_mb = speed / 1048576
            percentage = (c / t) * 100 if t and t > 0 else 0
            
            style_type = "block" if "📥" in action else "heartbeat"
            bar = get_progress_bar(percentage, style_type)
            escaped_action = html.escape(action)
            
            try: 
                await app.edit_message_text(
                    CHAT_ID, mid, 
                    f"▸ <b>Status:</b> {escaped_action}\n"
                    f"📊 <b>[{bar}] {percentage:.2f}%</b>\n"
                    f"📦 <code>{c/1048576:.1f}MB / {t/1048576:.1f}MB</code>\n"
                    f"⚡ <b>Speed:</b> <code>{speed_mb:.2f} MB/s</code>",
                    parse_mode="html",
                    reply_markup=get_cancel_markup()
                )
            except Exception as e: 
                print("Telegram progress update error:", e)
    except Exception as e:
        print("Uncaught exception in progress bar:", e)

# --- CONTEXTUAL DOWNLOAD HELPER ---
async def download_helper(app, input_id, file_name=None, progress=None, progress_args=None):
    try:
        msg_id = int(input_id)
        msg = await app.get_messages(CHAT_ID, msg_id)
        return await msg.download(file_name=file_name, progress=progress, progress_args=progress_args)
    except ValueError:
        return await app.download_media(input_id, file_name=file_name, progress=progress, progress_args=progress_args)

# --- FFPROBE HELPERS ---
def get_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except:
        return 0.0

def get_subtitle_streams(file_path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries", "stream=index", "-of", "csv=p=0", file_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        streams = res.stdout.strip().split('\n')
        return [s.strip() for s in streams if s.strip()]
    except:
        return []

# --- CLEAN SRT TAGS PARSER ---
def clean_srt_tags(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'{[^}]+}', '', text)
    return text.strip()

def convert_and_style_sub(sub_path, video_duration):
    def to_ass_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds % 1) * 100))
        if cs == 100:
            cs = 0; s += 1
            if s == 60: s = 0; m += 1
            if m == 60: m = 0; h += 1
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    end_time_str = to_ass_time(video_duration if video_duration > 0 else 36000)

    try:
        subs = pysubs2.load(sub_path, encoding="utf-8")
    except:
        subs = pysubs2.load(sub_path, encoding="latin-1")

    styled_ass = f"""[Script Info]
Title: ASI ASS Script - Complete & Cleaned
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ASI ᴀɴɪᴍᴇ_Watermark,Arial,140,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,2,9,10,40,40,1
Style: Default,Arial,90,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,-1,0,0,100,100,0,0,1,3.8,2,2,100,100,58,1
Style: Logo,Arial,30,&H00FFFFFF,&H00FFFFFF,&H000000FF,&H96000000,0,0,0,0,100,100,0,0,1,3,0,2,10,35,0.8,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 10,0:00:00.00,{end_time_str},ASI ᴀɴɪᴍᴇ_Watermark,,0000,0000,0000,,{{\\bord8\\blur5\\shad3}} {{\\c&HFF00FF&}}𝙰{{\\c&HFFFFFF&}}𝚂{{\\c&H00A0FF&}}𝙸☠
"""

    def mt(ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        cs = (ms % 1000) // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    for line in subs:
        if line.text.strip():
            clean_text = clean_srt_tags(line.text)
            clean_text = clean_text.replace('\n', '\\N').replace('\r', '')
            styled_ass += f"Dialogue: 0,{mt(line.start)},{mt(line.end)},Default,,0000,0000,0000,,{clean_text}\n"

    output_path = "styled_subtitle.ass"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(styled_ass)
    return output_path

# ================= DOWNLOAD STAGE =================
async def dl(app):
    global status_msg_id
    for temp_f in ["video.mp4", "out.mp4", "extracted_softsub.srt", "styled_subtitle.ass", "wm.png"]:
        if os.path.exists(temp_f):
            try: os.remove(temp_f)
            except: pass

    # Preparing Download status par bhi Cancel keyboard link kiya
    st = await app.send_message(
        CHAT_ID, 
        "⚙️ Worker: Preparing Download...",
        reply_markup=get_cancel_markup()
    )
    status_msg_id = st.id
    
    v = None
    for attempt in range(2):
        reset_prog()
        try:
            if os.path.exists("video.mp4"):
                try: os.remove("video.mp4")
                except: pass
                
            v = await download_helper(
                app, VIDEO_ID, file_name="video.mp4", 
                progress=prog, progress_args=(app, st.id, f"📥 Downloading Video (Attempt {attempt+1})...")
            )
            if v and os.path.exists(v) and os.path.getsize(v) > 50000:
                break
        except Exception as e:
            print(f"Download attempt failed: {e}")
            await asyncio.sleep(5)
    
    if not v or not os.path.exists(v) or os.path.getsize(v) < 1000:
        raise Exception("❌ Telegram side download error! Downloaded file is empty.")

    s, w = None, None
    if TASK_TYPE == "hsub":
        reset_prog()
        s = await download_helper(
            app, SUB_ID, 
            progress=prog, progress_args=(app, st.id, "📥 Downloading Subtitle...")
        )
        if WM_ID != "none": 
            reset_prog()
            w = await download_helper(
                app, WM_ID, file_name="wm.png", 
                progress=prog, progress_args=(app, st.id, "📥 Downloading Watermark...")
            )
            
    await app.edit_message_text(
        CHAT_ID, st.id, 
        "🔥 **Worker: Processing Started!**",
        reply_markup=get_cancel_markup()
    )
    return v, s, w, st.id

# ================= ENCODE & CONVERT STAGE =================
async def enc(app, v, s, w, mid):
    out = RENAME if RENAME != "none" else "out.mp4"
    out = os.path.basename(out)
    
    duration = get_duration(v)
    valid_res = RESO and RESO.strip().lower() not in ["none", "original", ""]
    extracted_sub = None
    
    if TASK_TYPE == "hsub":
        await app.edit_message_text(
            CHAT_ID, mid, 
            "⚙️ Worker: Encoding Hardsub...",
            reply_markup=get_cancel_markup()
        )
        styled_sub_path = convert_and_style_sub(s, duration)
        sub = os.path.abspath(styled_sub_path).replace('\\', '/')
        
        if valid_res:
            v_filter = f"scale=-2:{RESO},subtitles='{sub}':charenc=UTF-8"
        else:
            v_filter = f"scale='trunc(iw/2)*2:trunc(ih/2)*2',subtitles='{sub}':charenc=UTF-8"
            
        if w: 
            cmd = ["ffmpeg", "-y", "-i", v, "-i", w, "-filter_complex", f"[0:v]{v_filter}[sub];[1:v]scale=200:-1[wm];[sub][wm]overlay={'20:20' if WM_POS=='TL' else 'W-w-20:20'}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
        else: 
            cmd = ["ffmpeg", "-y", "-i", v, "-vf", v_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
            
    elif TASK_TYPE == "resize": 
        await app.edit_message_text(
            CHAT_ID, mid, 
            "⚙️ Worker: Compressing Video & Subtitle extraction...",
            reply_markup=get_cancel_markup()
        )
        if valid_res:
            scale_filter = f"scale=-2:{RESO}"
        else:
            scale_filter = "scale='trunc(iw/2)*2:trunc(ih/2)*2'"
        cmd = ["ffmpeg", "-y", "-i", v, "-vf", scale_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
        
        sub_streams = get_subtitle_streams(v)
        if sub_streams:
            extracted_sub = "extracted_softsub.srt"
            ext_cmd = ["ffmpeg", "-y", "-i", v, "-map", "0:s:0", "-c:s", "srt", extracted_sub]
            subprocess.run(ext_cmd, capture_output=True)
            if os.path.exists(extracted_sub) and os.path.getsize(extracted_sub) > 0:
                try:
                    tmp_subs = pysubs2.load(extracted_sub)
                    for line in tmp_subs:
                        line.text = clean_srt_tags(line.text)
                    tmp_subs.save(extracted_sub)
                except Exception as e:
                    print("Error cleaning soft subtitle:", e)
            else:
                extracted_sub = None
        
    elif TASK_TYPE == "extract": 
        await app.edit_message_text(
            CHAT_ID, mid, 
            "⚙️ Worker: Extracting Subtitle...",
            reply_markup=get_cancel_markup()
        )
        out = "extracted_sub.srt"
        cmd = ["ffmpeg", "-y", "-i", v, "-map", "0:s:0", "-c:s", "copy", out] 
    
    status_text = "Compressing Video" if TASK_TYPE == "resize" else "Encoding Hardsub"
    escaped_status = html.escape(status_text)
    
    cmd_with_progress = cmd[:-1] + ["-progress", "pipe:1", "-nostats"] + [cmd[-1]]
    process = await asyncio.create_subprocess_exec(
        *cmd_with_progress,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    speed = "0.00x"
    percentage = 0.0
    last_update = 0
    stderr_lines = []
    
    async def read_stdout():
        nonlocal speed, percentage, last_update
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_str = line.decode('utf-8', errors='ignore').strip()
            
            if "out_time_us=" in line_str:
                try:
                    us = int(line_str.split("=")[1])
                    cur_secs = us / 1000000.0
                    if duration > 0:
                        percentage = (cur_secs / duration) * 100
                        if percentage > 100.0: percentage = 100.0
                except:
                    pass
            elif "speed=" in line_str:
                speed = line_str.split("=")[1].strip()
            elif "progress=" in line_str:
                now = time.time()
                if now - last_update > 10 or line_str.endswith("end"):
                    bar = get_progress_bar(percentage, "dot")
                    escaped_speed = html.escape(speed)
                    try:
                        await app.edit_message_text(
                            CHAT_ID, mid,
                            f"▸ <b>Status:</b> {escaped_status}...\n"
                            f"📊 <b>[{bar}] {percentage:.2f}%</b>\n"
                            f"🚀 <b>Speed:</b> <code>{escaped_speed}</code>",
                            parse_mode="html",
                            reply_markup=get_cancel_markup()
                        )
                    except:
                        pass
                    last_update = now

    async def read_stderr():
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode('utf-8', errors='ignore'))
            
    await asyncio.gather(read_stdout(), read_stderr())
    await process.wait()
    
    return out, process.returncode, "".join(stderr_lines[-20:]), extracted_sub

# ================= UPLOAD STAGE =================
async def up(app, out, rc, err, mid, extracted_sub=None):
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        reset_prog()
        file_name = os.path.basename(out)
        
        await app.send_document(
            CHAT_ID, 
            document=out, 
            caption=f"✅ <b>{html.escape(file_name)}</b>", 
            parse_mode="html",
            progress=prog, 
            progress_args=(app, mid, "📤 Uploading Video...")
        )
        
        if extracted_sub and os.path.exists(extracted_sub) and os.path.getsize(extracted_sub) > 0:
            sub_name = file_name.rsplit(".", 1)[0] + ".srt"
            try:
                os.rename(extracted_sub, sub_name)
                await app.send_document(
                    CHAT_ID, 
                    document=sub_name, 
                    caption=f"📄 <b>Extracted Soft Subtitle:</b> <code>{html.escape(sub_name)}</code>",
                    parse_mode="html"
                )
            except Exception as e:
                print("Error uploading extracted soft subtitle:", e)
                
        await app.delete_messages(CHAT_ID, mid)
    else: 
        err_msg = err[-500:] if err else 'FFmpeg Error or Empty output'
        await app.edit_message_text(
            CHAT_ID, 
            mid, 
            f"❌ <b>Error:</b> <code>{html.escape(err_msg)}</code>", 
            parse_mode="html"
        )

# ================= RUN MASTER WITH FAIL-SAFE EXCEPTION EDITS =================
async def main():
    global status_msg_id
    app = Client("w_master", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    await app.start()
    
    try:
        v, s, w, mid = await dl(app)
        out, rc, err, extracted_sub = await enc(app, v, s, w, mid)
        await up(app, out, rc, err, mid, extracted_sub)
    except Exception as e:
        import traceback
        error_tb = traceback.format_exc()
        print(error_tb)
        try:
            # Agar crash pehle stage me hua, toh naya msg bhejne ke bajay usi ko edit karega
            if status_msg_id:
                await app.edit_message_text(
                    CHAT_ID, status_msg_id,
                    f"❌ <b>Worker Crash Error:</b>\n<code>{html.escape(str(e))}</code>",
                    parse_mode="html",
                    reply_markup=get_cancel_markup()
                )
            else:
                await app.send_message(
                    CHAT_ID,
                    f"❌ <b>Worker Crash Error:</b>\n<code>{html.escape(str(e))}</code>",
                    parse_mode="html",
                    reply_markup=get_cancel_markup()
                )
        except Exception as ex:
            print("Failed to send crash traceback to Telegram:", ex)
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
