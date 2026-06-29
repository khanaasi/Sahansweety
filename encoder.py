import os, sys, time, asyncio, subprocess, pyrogram.utils
from pyrogram import Client

# Pyrogram ID bug fix (Strictly from your commit)
pyrogram.utils.get_peer_type = lambda p: "channel" if str(p).startswith("-100") else "chat" if str(p).startswith("-") else "user"

# --- ENV VARIABLES ---
API_ID, API_HASH, BOT_TOKEN = int(os.getenv("API_ID")), os.getenv("API_HASH"), os.getenv("BOT_TOKEN")
TASK_TYPE, VIDEO_ID, SUB_ID = os.getenv("TASK_TYPE"), os.getenv("VIDEO_ID"), os.getenv("SUB_ID")
CHAT_ID, RESO, WM_ID = int(os.getenv("CHAT_ID")), os.getenv("RESOLUTION"), os.getenv("WM_ID")
WM_POS, RENAME = os.getenv("WM_POS"), os.getenv("RENAME")

last_time = 0
start_time = 0

# Progress details ko dynamic and clean reset karne ke liye helper
def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

# --- PROGRESS BAR (Speed, Size and Graphic Blocks) ---
async def prog(c, t, app, mid, action):
    global last_time, start_time
    now = time.time()
    if start_time == 0:
        start_time = now
        last_time = now
        return
        
    if now - last_time > 10 or c == t:
        elapsed = now - start_time
        speed = c / elapsed if elapsed > 0 else 0
        speed_mb = speed / 1048576
        percentage = (c / t) * 100
        # 10 blocks graphic progress bar
        bar = "▰" * int(percentage / 10) + "▱" * (10 - int(percentage / 10))
        
        try: 
            await app.edit_message_text(
                CHAT_ID, mid, 
                f"▸ **Status:** {action}\n"
                f"📊 `[{bar}] {percentage:.2f}%`\n"
                f"📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`\n"
                f"⚡ **Speed:** `{speed_mb:.2f} MB/s`"
            )
        except: 
            pass
        last_time = now

# --- FFPROBE HELPERS ---
def get_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        print("FFprobe duration error:", e)
        return 0.0

# --- FFMPEG REAL-TIME PARSER ---
async def run_ffmpeg_progress(cmd, duration, app, mid):
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
                if now - last_update > 8 or line_str.endswith("end"):
                    bar = "▰" * int(percentage / 10) + "▱" * (10 - int(percentage / 10))
                    try:
                        await app.edit_message_text(
                            CHAT_ID, mid,
                            f"▸ **Status:** Encoding Video...\n"
                            f"📊 `[{bar}] {percentage:.2f}%`\n"
                            f"🚀 **Speed:** `{speed}`"
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
    
    return process.returncode, "".join(stderr_lines[-20:])

# ================= STAGE 1: DOWNLOAD =================
async def dl(app):
    st = await app.send_message(CHAT_ID, "⚙️ Worker: Preparing Download...")
    
    reset_prog()
    v = await app.download_media(VIDEO_ID, file_name="video.mp4", progress=prog, progress_args=(app, st.id, "📥 Video..."))
    s, w = None, None
    
    if TASK_TYPE == "hsub":
        reset_prog()
        s = await app.download_media(SUB_ID, progress=prog, progress_args=(app, st.id, "📥 Subtitle..."))
        if WM_ID != "none": 
            reset_prog()
            w = await app.download_media(WM_ID, file_name="wm.png", progress=prog, progress_args=(app, st.id, "📥 Watermark..."))
            
    await app.edit_message_text(CHAT_ID, st.id, "🔥 **Worker: Processing Started!**")
    return v, s, w, st.id

# ================= STAGE 2: ENCODE (WITH REAL-TIME TRACKING) =================
async def enc(app, v, s, w, mid):
    out = RENAME if RENAME != "none" else "out.mp4"
    
    # SECURITY PATCH: Agar koi galti se rename me directory path ya slash '/' daal de, toh use clean karne ke liye
    out = os.path.basename(out)
    
    valid_res = RESO and RESO.strip().lower() not in ["none", "original", ""]
    
    if TASK_TYPE == "hsub":
        sub = os.path.abspath(s).replace('\\', '/')
        if valid_res:
            v_filter = f"scale=-2:{RESO},subtitles='{sub}':charenc=UTF-8"
        else:
            v_filter = f"scale='trunc(iw/2)*2:trunc(ih/2)*2',subtitles='{sub}':charenc=UTF-8"
            
        if w: 
            cmd = ["ffmpeg", "-y", "-i", v, "-i", w, "-filter_complex", f"[0:v]{v_filter}[sub];[1:v]scale=200:-1[wm];[sub][wm]overlay={'20:20' if WM_POS=='TL' else 'W-w-20:20'}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
        else: 
            cmd = ["ffmpeg", "-y", "-i", v, "-vf", v_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
            
    elif TASK_TYPE == "resize": 
        if valid_res:
            scale_filter = f"scale=-2:{RESO}"
        else:
            scale_filter = "scale='trunc(iw/2)*2:trunc(ih/2)*2'"
        cmd = ["ffmpeg", "-y", "-i", v, "-vf", scale_filter, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac", out]
        
    elif TASK_TYPE == "extract": 
        out = "extracted_sub.srt"
        cmd = ["ffmpeg", "-y", "-i", v, "-map", "0:s:0", "-c:s", "copy", out] 
    
    duration = get_duration(v)
    rc, err = await run_ffmpeg_progress(cmd, duration, app, mid)
    return out, rc, err

# ================= STAGE 3: UPLOAD =================
async def up(app, out, rc, err, mid):
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        reset_prog()
        file_name = os.path.basename(out)
        await app.send_document(
            CHAT_ID, 
            document=out, 
            caption=f"✅ **{file_name}**", 
            progress=prog, 
            progress_args=(app, mid, "📤 Uploading...")
        )
        await app.delete_messages(CHAT_ID, mid)
    else: 
        await app.edit_message_text(CHAT_ID, mid, f"❌ **Error:** `{err[-500:] if err else 'Unknown FFmpeg Error'}`")

# ================= RUN MASTER =================
async def main():
    app = Client("w_master", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    await app.start()
    
    v, s, w, mid = await dl(app)
    out, rc, err = await enc(app, v, s, w, mid)
    await up(app, out, rc, err, mid)
    
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
