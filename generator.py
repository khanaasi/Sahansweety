import os, time, asyncio, subprocess, pysubs2
import google.generativeai as genai
from pyrogram import Client
from faster_whisper import WhisperModel
import pyrogram.utils

pyrogram.utils.get_peer_type = lambda p: "channel" if str(p).startswith("-100") else "chat" if str(p).startswith("-") else "user"

API_ID, API_HASH, BOT_TOKEN = int(os.getenv("API_ID")), os.getenv("API_HASH"), os.getenv("BOT_TOKEN")
TASK_TYPE, FILE_ID, FORMAT_TYPE = os.getenv("TASK_TYPE"), os.getenv("FILE_ID"), os.getenv("FORMAT_TYPE")
CHAT_ID, MSG_ID = int(os.getenv("CHAT_ID")), int(os.getenv("MSG_ID"))
FILE_NAME, STYLE_TYPE = os.getenv("FILE_NAME", "sub"), os.getenv("STYLE_TYPE", "normal")
CUSTOM_PROMPT = os.getenv("CUSTOM_PROMPT", "none")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDcmpYpYI2RuntCa-ZNkuuE-u2uZFaqvQQ")
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

app, last_time, start_time = None, 0, 0

def reset_prog():
    global last_time, start_time
    last_time = time.time()
    start_time = time.time()

async def prog(c, t, action):
    global last_time, start_time
    try:
        now = time.time()
        if start_time == 0:
            start_time = now
            last_time = now
            return
            
        if now - last_time > 8 or c == t:
            elapsed = now - start_time
            speed = c / elapsed if elapsed > 0 else 0
            speed_mb = speed / 1048576
            percentage = (c / t) * 100 if t and t > 0 else 0
            bar = "▰" * int(percentage / 10) + "▱" * (10 - int(percentage / 10))
            
            try: 
                await app.edit_message_text(
                    CHAT_ID, MSG_ID, 
                    f"▸ **Status:** {action}\n"
                    f"📊 `[{bar}] {percentage:.2f}%`\n"
                    f"📦 `{c/1048576:.1f}MB / {t/1048576:.1f}MB`\n"
                    f"⚡ **Speed:** `{speed_mb:.2f} MB/s`"
                )
            except: 
                pass
            last_time = now
    except Exception as e:
        print("Progress callback error:", e)

def apply_asi(fp):
    subs = pysubs2.load(fp)
    if not subs: return
    ass = f"""[Script Info]
Title: ASI ASS Script - Complete & Fixed
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
Dialogue: 10,0:00:00.00,9:59:59.99,ASI ᴀɴɪᴍᴇ_Watermark,,0000,0000,0000,,{{\\bord8\\blur5\\shad3}} {{\\c&HFF00FF&}}𝙰{{\\c&HFFFFFF&}}𝚂{{\\c&H00A0FF&}}𝙸☠
"""
    def mt(ms): return f"{ms//3600000}:{(ms%3600000)//60000:02d}:{(ms%60000)//1000:02d}.{(ms%1000)//10:02d}"
    for l in subs: ass += f"Dialogue: 0,{mt(l.start)},{mt(l.end)},Default,,0000,0000,0000,,{l.text.replace(chr(10), '\\N')}\n"
    with open(fp, "w", encoding="utf-8") as f: f.write(ass)

def p_eng(vp):
    subprocess.run(["ffmpeg", "-i", vp, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "a.wav", "-y"], capture_output=True)
    m = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
    segs, _ = m.transcribe("a.wav", task="translate", vad_filter=True)
    subs = pysubs2.SSAFile()
    for s in segs:
        if s.text: subs.append(pysubs2.SSAEvent(start=int(s.start*1000), end=int(s.end*1000), text=s.text.strip()))
    out = f"{FILE_NAME}.{FORMAT_TYPE}"
    subs.save(out)
    if FORMAT_TYPE == "ass" and STYLE_TYPE == "asi_style": apply_asi(out)
    return out

def translate_with_gemini(texts):
    base_rules = """Translate the following subtitle lines into natural, conversational WhatsApp-style Hinglish.
RULES:
1. Translate the Hindi/English dialogue into natural Hinglish (conversational WhatsApp style).
2. Maintain the exact sequence mapping 'Index|||text'. Output must strictly be formatted as: Index|||TranslatedText
3. Do not drop or miss any index numbers.
4. Keep all formatting tags like {\\i1} or \\N as they are."""

    prompt = base_rules
    if CUSTOM_PROMPT != "none": prompt = f"{CUSTOM_PROMPT}\n\n{prompt}"
    
    formatted_text = "\n".join([f"{i}|||{txt}" for i, txt in enumerate(texts)])
    full_prompt = f"{prompt}\n\nTEXT TO TRANSLATE:\n{formatted_text}"
    
    try:
        response = ai_model.generate_content(full_prompt)
        res_lines = response.text.strip().split('\n')
        
        translated_dict = {}
        for line in res_lines:
            if "|||" in line:
                parts = line.split("|||", 1)
                try:
                    clean_idx = "".join(filter(str.isdigit, parts[0]))
                    if clean_idx:
                        translated_dict[int(clean_idx)] = parts[1].strip()
                except: pass
                
        final_texts = []
        for i in range(len(texts)):
            val = translated_dict.get(i, texts[i])
            if not val or val.strip() == "":
                val = texts[i]
            final_texts.append(val)
        return final_texts
    except Exception as e:
        print("Gemini Error:", e)
        return texts

def p_hi(sp):
    subs = pysubs2.load(sp)
    
    texts_to_translate = []
    valid_indices = []
    
    for i, l in enumerate(subs):
        if l.text.strip(): 
            texts_to_translate.append(l.text.strip())
            valid_indices.append(i)
            
    if texts_to_translate:
        # Safe batching of 40 lines to prevent Gemini timeouts or dropped sentences
        batch_size = 40
        for i in range(0, len(texts_to_translate), batch_size):
            batch_texts = texts_to_translate[i:i+batch_size]
            translated_batch = translate_with_gemini(batch_texts)
            
            for j, translated_txt in enumerate(translated_batch):
                if j < len(batch_texts):
                    subs[valid_indices[i+j]].text = translated_txt

    out = f"{FILE_NAME}_Hinglish.{FORMAT_TYPE}"
    subs.save(out)
    if FORMAT_TYPE == "ass" and STYLE_TYPE == "asi_style": apply_asi(out)
    return out

async def main():
    global app
    app = Client("ws", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
    await app.start()
    try:
        await app.edit_message_text(CHAT_ID, MSG_ID, "📥 Preparing download...")
        reset_prog()
        fp = await app.download_media(FILE_ID, progress=prog, progress_args=("📥 Downloading Video...",))
        
        # Complete corrupt check
        if not fp or not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            raise Exception("❌ Telegram side download error! Downloaded file is empty.")

        loop = asyncio.get_event_loop()
        if TASK_TYPE == "extract_english":
            await app.edit_message_text(CHAT_ID, MSG_ID, "⚙️ Generating English AI Subtitle...")
            out = await loop.run_in_executor(None, p_eng, fp)
            cap = f"✅ English Subtitle: `{FILE_NAME}.{FORMAT_TYPE}`"
        else:
            await app.edit_message_text(CHAT_ID, MSG_ID, "🤖 Translating via Gemini AI...")
            out = await loop.run_in_executor(None, p_hi, fp)
            cap = f"✅ AI Hinglish Subtitle: `{FILE_NAME}_Hinglish.{FORMAT_TYPE}`"
            
        reset_prog()
        await app.send_document(CHAT_ID, document=out, caption=cap, reply_to_message_id=MSG_ID, progress=prog, progress_args=("📤 Uploading...",))
        await app.delete_messages(CHAT_ID, MSG_ID)
    except Exception as e: await app.edit_message_text(CHAT_ID, MSG_ID, f"❌ Error: {e}")
    finally: await app.stop()

if __name__ == "__main__": asyncio.run(main())
