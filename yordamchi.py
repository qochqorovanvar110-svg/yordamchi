#!/usr/bin/env python3
"""Yordamchi: Claude'ning Pro limitini tejash uchun og'ir matn va video ishlarini Google modellariga beradi.

Ishlatish (Claude chaqiradi; Linux'da: python3 yordamchi.py ...):
  python -I D:\\TEMA\\yordamchi\\yordamchi.py [--daraja lite|flash|sonnet|opus] [-f FAYL ...] "vazifa"
  echo "matn" | python -I D:\\TEMA\\yordamchi\\yordamchi.py -f - "vazifa"
  python -I D:\\TEMA\\yordamchi\\yordamchi.py --video FAYL_YOKI_HAVOLA ["aniq savol"]
  python -I D:\\TEMA\\yordamchi\\yordamchi.py --holat

Darajalar va zanjir (birinchisi ishlamasa, keyingisiga o'tadi):
  lite   : API gemini-3.1-flash-lite -> agy gemini-3.8-flash-low
  flash  : API gemini-3.8-flash -> agy gemini-3.8-flash-high -> API gemini-3.1-flash-lite
  sonnet : agy claude-sonnet-4-6 -> agy gemini-3.8-flash-high
  opus   : agy claude-opus-4-6-thinking -> agy claude-sonnet-4-6

Video (--video): Gemini videoni kadrlari va ovozi bilan ko'radi (API gemini-3.8-flash -> gemini-3.1-flash-lite;
  --daraja lite bilan tartib teskari: avval tez va arzon lite).
  Havola (Instagram va h.k.) yt-dlp bilan vaqtincha yuklanadi; YouTube havolasi to'g'ridan-to'g'ri beriladi.
  Savol berilmasa to'liq hisobot chiqadi: nutq matni, ekrandagi yozuvlar, kadrlar, tekshiriladigan da'volar, reklama.
  Savol berilsa faqat o'sha savolga javob beriladi (qisqa va arzon).
  Vaqtincha fayllar (kompyuterda ham, Google'da ham) ish tugagach o'chiriladi.

Xavfsizlik: .env/kalit fayllari va matn ichidagi kalit/token ko'rinishidagi satrlar yuborilmaydi.
Bepul API darajasida yuborilgan narsa Google modellarini o'qitishda ishlatilishi mumkin: shaxsiy videolarni yubormang.
Kunlik chegara yo'q; limit tugasa provayderning o'zi rad etadi va zanjirdagi keyingi modelga o'tiladi.
Jurnal (matnsiz, faqat hajm va holat): Windows'da skript yonidagi jurnal.jsonl, boshqa tizimda ~/.yordamchi/jurnal.jsonl

Windows'dan boshqa tizimda (masalan, Claude cloud sessiyasi, Linux) "proksi rejimi" ishlaydi:
  - kalit skriptda bo'lmaydi: so'rov x-goog-api-key header'isiz ketadi, uni tarmoq proksisi (Network secret) qo'shadi;
    GEMINI_API_KEY o'zgaruvchisi berilgan bo'lsa, o'sha yuboriladi;
  - agy bo'lmagani uchun sonnet/opus darajalari xato beradi (jimgina boshqa modelga o'tmaydi);
  - Instagram kabi havolalar uchun yt-dlp o'rnatilgan va o'sha saytlar tarmoqda ochiq bo'lishi kerak;
    YouTube havolalari va matn ishlari uchun faqat generativelanguage.googleapis.com yetarli.
"""
import argparse
import datetime as dt
import http.client
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
try:
    import winreg
except ImportError:  # Linux/macOS (masalan, Claude cloud sessiyasi)
    winreg = None

VERSIYA = "2026-11-17.2"
PAPKA = os.path.dirname(os.path.abspath(__file__))
# Proksi rejimi (Claude cloud): kalit skriptda bo'lmaydi, uni tarmoq proksisi so'rovga o'zi qo'shadi.
PROKSI = os.name != "nt" or os.environ.get("YORDAMCHI_PROKSI") == "1"
# Jurnal va vaqtincha fayllar: Windows'da skript yonida, boshqa tizimda ~/.yordamchi (yoki YORDAMCHI_PAPKA).
MALUMOT = PAPKA if os.name == "nt" else (
    os.environ.get("YORDAMCHI_PAPKA") or os.path.join(os.path.expanduser("~"), ".yordamchi"))
JURNAL = os.path.join(MALUMOT, "jurnal.jsonl")
AGY = r"D:\TEMA\agy\bin\agy.exe"
AGY_ISH = r"D:\TEMA\agy-ish"
API_ASOS = "https://generativelanguage.googleapis.com/v1beta/{}"
API_URL = API_ASOS.format("models/{}:generateContent")
YUKLASH_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"

ZANJIR = {
    "lite": [("api", "gemini-3.1-flash-lite"), ("agy", "gemini-3.8-flash-low")],
    "flash": [("api", "gemini-3.8-flash"), ("agy", "gemini-3.8-flash-high"), ("api", "gemini-3.1-flash-lite")],
    "sonnet": [("agy", "claude-sonnet-4-6"), ("agy", "gemini-3.8-flash-high")],
    "opus": [("agy", "claude-opus-4-6-thinking"), ("agy", "claude-sonnet-4-6")],
}
VIDEO_ZANJIR = ["gemini-3.8-flash", "gemini-3.1-flash-lite"]
# Kunlik chegara yo'q (foydalanuvchi so'roviga ko'ra, 2026-11-15); --holat faqat sanaydi.
MODELLAR = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.8-flash-low",
            "gemini-3.8-flash-high", "claude-sonnet-4-6", "claude-opus-4-6-thinking"]

YOUTUBE_ID = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/)|youtu\.be/)"
                        r"([A-Za-z0-9_\-]{11})", re.I)
VIDEO_MAX_BAYT = 1_900_000_000
VIDEO_SOROV = """You are a careful video analyst writing notes for a fact-checker who cannot watch the video. \
Watch and listen to the whole video. Report only what is actually seen or heard; write [unclear] instead of guessing. \
Be compact: no introduction, no conclusion.

1. SUMMARY: 2-3 sentences: what the video is and what it wants the viewer to believe or do.
2. SPEECH: verbatim transcript in the original language, with a [mm:ss] mark every few sentences. Name the language \
and say if the voice sounds AI-generated or dubbed. If there is no speech, say so.
3. ON-SCREEN TEXT: every caption, title, number, logo, brand name, username and watermark, each with [mm:ss].
4. VISUALS: scene by scene with [mm:ss], one line each: what is shown (people, places, maps, charts, screen \
recordings) and whether the footage looks like stock, AI-generated or re-uploaded material.
5. CLAIMS: numbered list of every checkable factual claim (numbers, dates, names, cause and effect), each with \
[mm:ss] and whether it was spoken or shown on screen.
6. PROMOTION: any advert, product, service, link, "comment X and I will DM you" bait or other call to action.
7. SOUND: background music or sound effects worth noting, one line."""
VIDEO_SAVOL = ("Watch and listen to the whole video, then answer the question below. Use only what is actually seen "
               "or heard in the video; say so if the video does not show it. Be compact.\n\nQuestion: ")

MAXFIY_NOM = re.compile(r"(^|[\\/])(\.env[^\\/]*|id_rsa[^\\/]*|id_ed25519[^\\/]*|[^\\/]*\.(pem|key|p12|pfx|kdbx)|"
                        r"[^\\/]*(credential|secret|token|password|parol)[^\\/]*)$", re.I)
MAXFIY_MATN = {
    "Google API kaliti": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI/Anthropic kaliti": re.compile(r"\bsk-(ant-)?[A-Za-z0-9_\-]{20,}"),
    "Telegram bot tokeni": re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"),
    "maxfiy kalit (PEM)": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub tokeni": re.compile(r"\b(ghp|gho|ghu|ghs)_[A-Za-z0-9]{36}\b|github_pat_[A-Za-z0-9_]{50,}"),
    "AWS kaliti": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack tokeni": re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}"),
    "Supabase maxfiy kaliti": re.compile(r"\bsb_secret_[A-Za-z0-9_\-]{20,}"),
    "JWT token": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "Mapbox maxfiy tokeni": re.compile(r"\bsk\.eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
    "ElevenLabs kaliti": re.compile(r"\bsk_[0-9a-f]{40,}\b"),
}
# Muhit o'zgaruvchilaridagi kalit/token qiymatlari (main() to'ldiradi): matnda uchrasa, yuborilmaydi.
MUHIT_SIRLARI = {}
# Nom bo'lagi to'liq so'z bo'lishi kerak: GEMINI_API_KEY, BOT_TOKEN ushlanadi; KEYBOARD, TOKENIZERS, MONKEY emas.
MUHIT_NOMI = re.compile(r"(?:^|_)(?:API_?KEY|KEY|TOKEN|SECRET|PASS|PASSWORD|PASSWD|PAROL|CREDENTIALS?)(?:_|$)", re.I)
# Ulanish uzilishi, chala javob va h.k. (URLError, TimeoutError, ConnectionError hammasi OSError ichida).
TARMOQ_XATOLARI = (OSError, http.client.HTTPException)


def xato(matn, kod=2):
    print(f"[yordamchi] XATO: {matn}", file=sys.stderr)
    sys.exit(kod)


def gemini_kaliti():
    if winreg and not PROKSI:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            qiymat, _ = winreg.QueryValueEx(k, "GEMINI_API_KEY")
            if qiymat.strip():
                return qiymat.strip()
        except OSError:
            pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def api_sarlavha(kalit, qoshimcha=None):
    """Kalit bo'lsa header'ga qo'yadi; proksi rejimida kalitsiz ketadi va uni proksi qo'shadi."""
    s = dict(qoshimcha or {})
    if kalit:
        s["x-goog-api-key"] = kalit
    return s


def sirga_oxshaydi(q):
    """Qisqa qiymat, mavjud fayl yo'li va login-parolsiz havola sir emas; qolgani sir deb olinadi."""
    if len(q) < 16:
        return False
    if "://" in q:
        return "@" in q.split("://", 1)[1].split("/", 1)[0]
    try:
        return not os.path.exists(os.path.expanduser(q))
    except (OSError, ValueError):
        return True


def muhit_sirlari(kalit):
    sirlar = {nom: q.strip() for nom, q in os.environ.items()
              if MUHIT_NOMI.search(nom) and sirga_oxshaydi(q.strip())}
    if len(kalit) >= 16:
        sirlar["GEMINI_API_KEY"] = kalit
    return sirlar


def bugungi_hisob():
    bugun = dt.date.today().isoformat()
    hisob = {}
    if os.path.exists(JURNAL):
        with open(JURNAL, encoding="utf-8") as f:
            for qator in f:
                try:
                    y = json.loads(qator)
                except ValueError:
                    continue
                if y.get("vaqt", "").startswith(bugun) and y.get("holat") == "ok":
                    hisob[y["model"]] = hisob.get(y["model"], 0) + 1
    return hisob


def yoz_jurnal(**y):
    y["vaqt"] = dt.datetime.now().isoformat(timespec="seconds")
    try:
        os.makedirs(MALUMOT, exist_ok=True)
        with open(JURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    except OSError:
        pass  # jurnal yozilmasa ham javob berilaveradi


def tekshir_maxfiy(nom, matn):
    if nom != "-" and MAXFIY_NOM.search(nom):
        xato(f"'{nom}' maxfiy fayl nomiga o'xshaydi, yuborilmadi.")
    for tur, rx in MAXFIY_MATN.items():
        if rx.search(matn):
            xato(f"'{nom}' ichida {tur} ko'rinishidagi satr bor, yuborilmadi. Avval uni olib tashlang.")
    for ozgaruvchi, qiymat in MUHIT_SIRLARI.items():
        if qiymat in matn:
            xato(f"'{nom}' ichida {ozgaruvchi} muhit o'zgaruvchisining qiymati bor, yuborilmadi.")


def fayllarni_oqi(yollar):
    natija = []
    for y in yollar:
        if y == "-":
            matn = sys.stdin.buffer.read().decode("utf-8", errors="replace")
            nom = "stdin.txt"
        else:
            if not os.path.isfile(y):
                xato(f"fayl topilmadi: {y}")
            with open(y, "rb") as f:
                xom = f.read()
            if b"\x00" in xom[:4096]:
                xato(f"'{y}' matn fayli emas (binar), yuborilmadi.")
            matn = xom.decode("utf-8", errors="replace")
            nom = os.path.basename(y)
        tekshir_maxfiy(y, matn)
        natija.append((nom, matn))
    return natija


def http_izoh(e):
    try:
        return f"HTTP {e.code}: " + json.loads(e.read().decode("utf-8", "replace"))["error"]["message"][:200]
    except Exception:
        return f"HTTP {e.code}"


def api_chaqir(model, vazifa, fayllar, kalit, max_chiqish, video=None, past_sifat=False, urinishlar=3):
    qismlar = []
    if video:
        mime, uri = video
        qismlar.append({"file_data": {"mime_type": mime, "file_uri": uri} if mime else {"file_uri": uri}})
    qismlar.append({"text": vazifa})
    for nom, matn in fayllar:
        qismlar.append({"text": f"\n=== FAYL: {nom} ===\n{matn}"})
    sozlama = {"maxOutputTokens": max_chiqish}
    if past_sifat:
        sozlama["mediaResolution"] = "MEDIA_RESOLUTION_LOW"
    tana = {"contents": [{"role": "user", "parts": qismlar}], "generationConfig": sozlama}
    so = urllib.request.Request(API_URL.format(model), data=json.dumps(tana).encode("utf-8"),
                                headers=api_sarlavha(kalit, {"Content-Type": "application/json"}))
    for urinish in range(urinishlar):
        try:
            javob = json.load(urllib.request.urlopen(so, timeout=600 if video else 300))
            nomzod = (javob.get("candidates") or [{}])[0]
            matn = "".join(p.get("text", "") for p in nomzod.get("content", {}).get("parts", []))
            if not matn.strip():
                return None, f"bo'sh javob ({nomzod.get('finishReason')})", javob.get("usageMetadata")
            if nomzod.get("finishReason") == "MAX_TOKENS":
                print("[yordamchi] DIQQAT: javob oxirigacha yetmay kesildi (--max-chiqish ni oshiring)", file=sys.stderr)
            return matn, None, javob.get("usageMetadata")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and urinish < urinishlar - 1:
                time.sleep(3 + urinish * 5)
                continue
            return None, http_izoh(e), None
        except TARMOQ_XATOLARI + (ValueError,) as e:
            # Ulanish uzildi yoki javob chala keldi: vaqt tugashidan boshqa holatda qayta urinamiz.
            vaqt_tugadi = isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError)
            if not vaqt_tugadi and urinish < urinishlar - 1:
                time.sleep(3 + urinish * 5)
                continue
            return None, f"tarmoq: {type(e).__name__}: {e}", None
    return None, "urinishlar tugadi", None


def agy_chaqir(model, vazifa, fayllar, vaqt_chegarasi):
    if not os.path.exists(AGY):
        return None, "agy topilmadi"
    ish_id = uuid.uuid4().hex[:8]
    kirish = os.path.join(AGY_ISH, "_kirish", ish_id)
    try:
        nisbiy = []
        if fayllar:
            os.makedirs(kirish)
            for nom, matn in fayllar:
                with open(os.path.join(kirish, nom), "w", encoding="utf-8") as f:
                    f.write(matn)
                nisbiy.append(f"_kirish/{ish_id}/{nom}")
        sorov = vazifa
        if nisbiy:
            sorov += ("\n\nInput files (read them; do not modify any file, do not run commands; "
                      "answer directly, without file links or line citations): " + ", ".join(nisbiy))
        if len(sorov) > 30000:
            return None, "vazifa matni juda uzun (uni -f bilan fayl qilib bering)"
        buyruq = [AGY, "--mode", "plan", "--model", model, "--print-timeout", f"{vaqt_chegarasi}s",
                  "--disable-slash-commands", "-p", sorov]
        try:
            p = subprocess.run(buyruq, cwd=AGY_ISH, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=vaqt_chegarasi + 60)
        except subprocess.TimeoutExpired:
            return None, "vaqt tugadi"
        chiqish = p.stdout.strip()
        if p.returncode != 0 or not chiqish:
            izoh = "\n".join(q for q in p.stderr.splitlines() if "logging before google.Init" not in q)
            return None, f"agy kod {p.returncode}: {izoh.strip()[-300:]}"
        if re.search(r"quota|rate limit|exhausted|resource_exhausted", chiqish[:400], re.I) and len(chiqish) < 600:
            return None, f"agy limiti: {chiqish[:200]}"
        return chiqish, None
    finally:
        shutil.rmtree(kirish, ignore_errors=True)


def video_yukla(havola, papka):
    """Havoladagi videoni yt-dlp bilan papkaga yuklaydi. (fayl yo'li, info dict, xato) qaytaradi."""
    os.makedirs(papka)
    if importlib.util.find_spec("yt_dlp"):
        buyruq = [sys.executable] + (["-I"] if sys.flags.isolated else []) + ["-m", "yt_dlp"]
    elif shutil.which("yt-dlp"):
        buyruq = [shutil.which("yt-dlp")]
    else:
        return None, {}, "yt-dlp o'rnatilmagan (pip install yt-dlp). YouTube havolalari usiz ham ishlaydi."
    buyruq += ["--no-playlist", "--no-warnings", "-q",
               "-f", "b[height<=720]/bv*[height<=720]+ba/b/bv*+ba", "--merge-output-format", "mp4",
               "--max-filesize", "400M", "--write-info-json", "-o", os.path.join(papka, "video.%(ext)s")]
    try:
        import imageio_ffmpeg
        buyruq += ["--ffmpeg-location", imageio_ffmpeg.get_ffmpeg_exe()]
    except Exception:
        pass  # tizimdagi ffmpeg'ni yt-dlp o'zi topadi
    try:
        p = subprocess.run(buyruq + [havola], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900, cwd=papka)
    except subprocess.TimeoutExpired:
        return None, {}, "yuklash vaqti tugadi"
    if p.returncode != 0:
        return None, {}, f"yt-dlp: {p.stderr.strip()[-300:]}"
    info, yol = {}, None
    for nom in os.listdir(papka):
        toliq = os.path.join(papka, nom)
        if nom.endswith(".info.json"):
            try:
                with open(toliq, encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                pass
        elif not nom.endswith((".json", ".part", ".ytdl")):
            yol = toliq
    if not yol:
        return None, info, "video fayli tushmadi (400 MB dan katta bo'lishi mumkin)"
    return yol, info, None


def malumot_satrlari(info):
    """yt-dlp info.json'dan Claude uchun qisqa sarlavha."""
    qism = []
    for kalit, nom in (("uploader", "muallif"), ("channel", "kanal"), ("upload_date", "sana"),
                       ("duration", "soniya"), ("view_count", "korishlar"), ("like_count", "layk"),
                       ("comment_count", "izoh")):
        if info.get(kalit) not in (None, ""):
            qism.append(f"{nom}={info[kalit]}")
    satrlar = ["[video] " + ", ".join(qism)] if qism else []
    tavsif = (info.get("description") or info.get("title") or "").strip()
    if tavsif:
        satrlar.append("[caption] " + tavsif[:1500])
    return satrlar


def gemini_yukla(yol, mime, kalit):
    """Faylni Gemini Files API'ga yuklab, tayyor bo'lishini kutadi. (fayl nomi, uri, xato) qaytaradi."""
    hajm = os.path.getsize(yol)
    nom = None
    try:
        bosh = urllib.request.Request(
            YUKLASH_URL, data=json.dumps({"file": {"display_name": "video"}}).encode("utf-8"),
            headers=api_sarlavha(kalit, {
                "Content-Type": "application/json",
                "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(hajm), "X-Goog-Upload-Header-Content-Type": mime}))
        with urllib.request.urlopen(bosh, timeout=60) as j:
            manzil = j.headers.get("X-Goog-Upload-URL")
        if not manzil:
            return None, None, "yuklash manzili kelmadi"
        with open(yol, "rb") as f:
            so = urllib.request.Request(manzil, data=f, method="POST",
                                        headers={"Content-Length": str(hajm), "X-Goog-Upload-Offset": "0",
                                                 "X-Goog-Upload-Command": "upload, finalize"})
            with urllib.request.urlopen(so, timeout=1800) as j:
                fayl = json.load(j)["file"]
        nom = fayl.get("name")
        for _ in range(200):
            if fayl.get("state") == "ACTIVE":
                return nom, fayl["uri"], None
            if fayl.get("state") == "FAILED":
                return nom, None, "Gemini videoni qayta ishlay olmadi"
            time.sleep(3)
            so = urllib.request.Request(API_ASOS.format(nom), headers=api_sarlavha(kalit))
            with urllib.request.urlopen(so, timeout=60) as j:
                fayl = json.load(j)
        return nom, None, "Gemini videoni tayyorlashi juda uzoq cho'zildi"
    except urllib.error.HTTPError as e:
        return nom, None, "yuklash " + http_izoh(e)
    except TARMOQ_XATOLARI + (KeyError, ValueError) as e:
        return nom, None, f"yuklash: {e}"


def gemini_ochir(nom, kalit):
    try:
        so = urllib.request.Request(API_ASOS.format(nom), method="DELETE", headers=api_sarlavha(kalit))
        urllib.request.urlopen(so, timeout=30).close()
    except TARMOQ_XATOLARI:
        pass


def video_ishi(a, kalit):
    if not kalit and not PROKSI:
        xato("GEMINI_API_KEY yo'q: video faqat Gemini API orqali ishlaydi")
    manba = a.video
    havola = re.match(r"^https?://", manba, re.I) is not None
    sorov = VIDEO_SAVOL + a.vazifa if a.vazifa else VIDEO_SOROV
    ish = os.path.join(MALUMOT, "_video", uuid.uuid4().hex[:8])
    gemini_nom, sarlavha, hajm = None, [], 0
    try:
        yt = YOUTUBE_ID.search(manba) if havola else None
        if yt:
            video = (None, "https://www.youtube.com/watch?v=" + yt.group(1))
        else:
            if havola:
                yol, info, xat = video_yukla(manba, ish)
                if xat:
                    xato(xat, kod=3)
                sarlavha = malumot_satrlari(info)
            else:
                yol = manba
                if not os.path.isfile(yol):
                    xato(f"fayl topilmadi: {yol}")
                if MAXFIY_NOM.search(yol):
                    xato(f"'{yol}' maxfiy fayl nomiga o'xshaydi, yuborilmadi.")
            hajm = os.path.getsize(yol)
            if hajm > VIDEO_MAX_BAYT:
                xato("video 1.9 GB dan katta, Gemini qabul qilmaydi")
            mime = mimetypes.guess_type(yol)[0] or "video/mp4"
            if not mime.startswith(("video/", "audio/", "image/")):
                xato(f"'{yol}' video, audio yoki rasm emas ({mime})")
            gemini_nom, uri, xat = gemini_yukla(yol, mime, kalit)
            if xat:
                xato(xat, kod=3)
            video = (mime, uri)
        sabablar = []
        # Bepul darajada 3.8-flash tez-tez 503 beradi: birinchi modelga bir marta urinib, darrov keyingisiga o'tamiz.
        tartib = VIDEO_ZANJIR[::-1] if a.daraja == "lite" else VIDEO_ZANJIR
        for i, model in enumerate(tartib + tartib):
            if i == len(tartib):
                # Ikkala model ham band (503/429) bo'lsa, biroz kutib yana bir aylanamiz; boshqa xatoda to'xtaymiz.
                if not all("HTTP 503" in s or "HTTP 429" in s for s in sabablar):
                    break
                time.sleep(20)
            oxirgi = i % len(tartib) == len(tartib) - 1
            boshl = time.time()
            matn, xat, ishlatilgan = api_chaqir(model, sorov, [], kalit, a.max_chiqish or 16384, video=video,
                                                past_sifat=a.past_sifat, urinishlar=3 if oxirgi else 1)
            soniya = round(time.time() - boshl, 1)
            yoz_jurnal(daraja="video", tur="api", model=model, kirish_belgi=len(sorov), video_bayt=hajm,
                       chiqish_belgi=len(matn or ""), soniya=soniya, holat="ok" if matn else "xato",
                       sabab=xat, tokenlar=ishlatilgan)
            if matn:
                print(f"[yordamchi] video api:{model} {soniya}s", file=sys.stderr)
                for s in sarlavha:
                    print(s)
                print(matn)
                return
            sabablar.append(f"{model}: {xat}")
        xato("hech bir model videoni tahlil qilmadi -> " + "; ".join(sabablar), kod=3)
    finally:
        if gemini_nom:
            gemini_ochir(gemini_nom, kalit)
        shutil.rmtree(ish, ignore_errors=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Claude uchun yordamchi model chaqiruvchi")
    ap.add_argument("vazifa", nargs="?", help="modelga topshiriq (prompt)")
    ap.add_argument("-f", "--fayl", action="append", default=[], help="kirish fayli; '-' = stdin")
    ap.add_argument("--daraja", choices=list(ZANJIR), default="flash")
    ap.add_argument("--video", help="video fayli yoki havolasi (Instagram, YouTube...); Gemini ko'rib-eshitib tahlil qiladi")
    ap.add_argument("--past-sifat", action="store_true", help="video kadrlarini past aniqlikda o'qish (uzun video uchun arzon)")
    ap.add_argument("--max-chiqish", type=int, help="API uchun javob tokenlari chegarasi (matn 8192, video 16384)")
    ap.add_argument("--vaqt", type=int, default=300, help="agy uchun soniyalar")
    ap.add_argument("--holat", action="store_true", help="bugungi foydalanishni ko'rsatish")
    ap.add_argument("--versiya", action="store_true", help="skript versiyasini ko'rsatish")
    a = ap.parse_args()

    if a.versiya:
        print(VERSIYA)
        return
    kalit = gemini_kaliti()
    MUHIT_SIRLARI.update(muhit_sirlari(kalit))
    hisob = bugungi_hisob()
    if a.holat:
        kalit_holati = "bor" if kalit else ("proksi qo'shadi" if PROKSI else "YO'Q")
        agy_holati = "bor" if os.path.exists(AGY) else "yo'q"
        print(f"Versiya {VERSIYA}; kalit: {kalit_holati}; agy: {agy_holati}; jurnal: {JURNAL}")
        print("Bugun:", dt.date.today().isoformat())
        for m in MODELLAR:
            print(f"  {m:28s} {hisob.get(m, 0):4d} ta")
        return
    if a.video:
        if a.vazifa:
            tekshir_maxfiy("vazifa", a.vazifa)
        if a.fayl:
            xato("--video bilan -f birga ishlatilmaydi")
        video_ishi(a, kalit)
        return
    if not a.vazifa:
        xato("vazifa matni berilmadi")
    tekshir_maxfiy("vazifa", a.vazifa)
    fayllar = fayllarni_oqi(a.fayl)
    hajm = len(a.vazifa) + sum(len(m) for _, m in fayllar)
    max_chiqish = a.max_chiqish or 8192

    sabablar = []
    for tur, model in ZANJIR[a.daraja]:
        boshl = time.time()
        if tur == "api":
            if not kalit and not PROKSI:
                sabablar.append(f"{model}: GEMINI_API_KEY yo'q")
                continue
            matn, xat, ishlatilgan = api_chaqir(model, a.vazifa, fayllar, kalit, max_chiqish)
        else:
            matn, xat = agy_chaqir(model, a.vazifa, fayllar, a.vaqt)
            ishlatilgan = None
        soniya = round(time.time() - boshl, 1)
        yoz_jurnal(daraja=a.daraja, tur=tur, model=model, kirish_belgi=hajm,
                   chiqish_belgi=len(matn or ""), soniya=soniya, holat="ok" if matn else "xato",
                   sabab=xat, tokenlar=ishlatilgan)
        if matn:
            print(f"[yordamchi] {tur}:{model} {soniya}s", file=sys.stderr)
            print(matn)
            return
        sabablar.append(f"{model}: {xat}")
    xato("hech bir model javob bermadi -> " + "; ".join(sabablar), kod=3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:  # kutilmagan xato: uzun traceback o'rniga bitta qator (YORDAMCHI_DEBUG=1 to'liq ko'rsatadi)
        if os.environ.get("YORDAMCHI_DEBUG") == "1":
            raise
        xato(f"kutilmagan xato: {type(e).__name__}: {e}", kod=4)
