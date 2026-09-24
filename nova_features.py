"""
nova_features.py - paket fitur tambahan untuk Nova.
Letakkan di folder yang sama dengan nova_assistant.py. Nova memuatnya otomatis.

Menambah fitur sendiri: cukup tulis fungsi baru dengan dekorator @cmd(...):

    @cmd("katakan halo dunia")
    def h_contoh(b, c, m):
        b.say("Halo dunia!")

b = Brain (b.say untuk bicara, b.app.log untuk menulis ke layar), c = perintah huruf kecil,
m = hasil regex (jika memakai rx=). Kembalikan False bila perintah ternyata bukan untuknya.
"""
import os
import re
import json
import math
import time
import random
import string
import secrets
import socket
import shutil
import threading
import subprocess
import datetime
import webbrowser
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    import pyautogui
except Exception:
    pyautogui = None
try:
    import psutil
except Exception:
    psutil = None
try:
    import winsound
except Exception:
    winsound = None

# ---------------------------------------------------------
# PENGATURAN (ubah sesuai kebutuhan)
# ---------------------------------------------------------
DEFAULT_CITY = "Jakarta"      # kota bawaan untuk cuaca & jadwal salat
COUNTRY = "Indonesia"
DATA_FILE = "nova_data.json"  # tugas, agenda, dan nama panggilan
PHOTO_FOLDER = "photos"

NOWIN = 0x08000000 if os.name == "nt" else 0
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["januari", "februari", "maret", "april", "mei", "juni", "juli",
         "agustus", "september", "oktober", "november", "desember"]

# =========================================================
# INFRASTRUKTUR
# =========================================================

REGISTRY = []


def cmd(*triggers, rx=None):
    def deco(fn):
        REGISTRY.append((triggers, re.compile(rx) if rx else None, fn))
        return fn
    return deco


def ask(b, question, action):
    b.awaiting = action
    b.say(question + " Katakan ya untuk melanjutkan, atau tidak untuk membatalkan.")


def dispatch(b, c):
    """Dipanggil Brain sebelum perintah bawaan. Mengembalikan True bila perintah sudah ditangani."""
    if b.awaiting:
        action, b.awaiting = b.awaiting, None
        if re.search(r"\b(ya|iya|lanjutkan|lanjut|oke|ok|yakin|boleh)\b", c):
            action()
            return True
        if re.search(r"\b(tidak|batal|jangan|nggak|enggak)\b", c):
            b.say("Baik, dibatalkan.")
            return True
    if b.mode == "dictation":
        return dictate(b, c)
    if b.game and play_game(b, c):
        return True
    for triggers, rx, fn in REGISTRY:
        m = rx.search(c) if rx else None
        if m or any(t in c for t in triggers):
            try:
                if fn(b, c, m) is not False:
                    return True
            except (urllib.error.URLError, socket.timeout):
                b.say("Koneksi internet bermasalah. Coba lagi nanti.")
                return True
            except Exception as error:
                b.app.log("sys", f"Fitur gagal ({fn.__name__}): {error}")
                b.say("Maaf, fitur itu gagal dijalankan.")
                return True
    return False


def http_get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "NovaAssistant/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, timeout=8):
    return json.loads(http_get(url, timeout).decode("utf-8"))


def q(text):
    return urllib.parse.quote(text)


def num(text):
    return float(text.replace(",", "."))


def fmt(x):
    if float(x).is_integer():
        return f"{int(x):,}".replace(",", ".")
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


_lock = threading.Lock()


def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("tasks", [])
    d.setdefault("agenda", [])
    d.setdefault("name", "")
    return d


def save(d):
    with _lock, open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def set_clipboard(text):
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:NOVA_TXT"],
                   env=dict(os.environ, NOVA_TXT=text), creationflags=NOWIN)


def get_clipboard():
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                       capture_output=True, text=True, creationflags=NOWIN)
    return (r.stdout or "").strip()


def keys(*k):
    if pyautogui is None:
        raise RuntimeError("pyautogui belum terpasang")
    pyautogui.hotkey(*k) if len(k) > 1 else pyautogui.press(k[0])


def beep():
    if winsound:
        for _ in range(3):
            try:
                winsound.Beep(1000, 250)
            except Exception:
                pass
            time.sleep(0.1)


def start_proc(target):
    subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=NOWIN)


# =========================================================
# BANTUAN
# =========================================================

HELP = {
    "waktu": "jam berapa di Tokyo • berapa hari lagi ke 17 agustus • jadwal salat • salat berikutnya • waktu magrib",
    "pengingat": "timer 10 menit • alarm jam 6 pagi • ingatkan saya minum obat 30 menit lagi • ingatkan saya minum air setiap 1 jam • daftar pengingat • batalkan semua pengingat • mulai pomodoro • mulai stopwatch • berhenti stopwatch",
    "produktivitas": "tambah tugas beli tinta • daftar tugas • selesaikan tugas 2 • hapus tugas 2 • hapus semua tugas • tambah agenda rapat besok jam 10 • agenda hari ini • agenda besok • catat ... • baca catatan • mulai mendikte",
    "internet": "cuaca di Medan • cuaca besok • apakah akan hujan • apa itu fotosintesis • siapa itu Habibie • berita terbaru • berita olahraga • kurs dolar • 10 euro ke rupiah • terjemahkan selamat pagi ke bahasa inggris • cek internet • ip address • nama wifi",
    "komputer": "info sistem • penggunaan cpu • sisa penyimpanan • lama komputer menyala • baterai • aplikasi yang berjalan • atur volume 40 persen • kecerahan 60 • mode gelap • mode terang • kunci layar • matikan komputer • restart komputer • tidurkan komputer • batalkan shutdown",
    "jendela": "tampilkan desktop • ganti jendela • tab baru • tutup tab • refresh • layar penuh • perbesar • salin • tempel • pilih semua • urungkan • simpan file • rekam layar • potong layar • tekan enter • gulir ke bawah • ketik halo apa kabar",
    "media": "putar musik • jeda musik • lagu berikutnya • putar lagu Dewa 19 • cari video ... • cari gambar kucing",
    "file": "cari file laporan • buka file pertama • file terbaru • rapikan downloads • buat folder Proyek • jumlah file di downloads • kosongkan recycle bin • bacakan clipboard • salin teks halo",
    "aplikasi": "buka Word • buka Spotify • buka WhatsApp • buka kamera • buka tokopedia • buka github.com • tutup aplikasi chrome • rute ke bandara • restoran terdekat • cari harga laptop • kirim pesan whatsapp ke 0812xxxx isi halo",
    "hitung": "hitung 12 kali 8 • 15 persen dari 200 • akar 144 • 2 pangkat 10 • 5 km ke mil • 30 celsius ke fahrenheit • 2 kg ke pon",
    "hiburan": "beri aku lelucon • kutipan motivasi • fakta menarik • pantun • teka-teki • lempar koin • lempar dadu • angka acak 1 sampai 100 • pilih pizza atau nasi goreng • buat kata sandi • main tebak angka • main suit",
    "nova": "bicara lebih cepat • bicara lebih pelan • ganti suara ke Ardi • ulangi • bersihkan chat • panggil saya Budi • siapa namaku • ambil foto",
}


@cmd("bantuan", "daftar fitur", "fitur apa", "bisa apa", "apa saja yang bisa")
def h_help(b, c, m):
    for k, v in HELP.items():
        if re.search(rf"\b{k}\b", c):
            b.app.log("sys", f"{k}:\n" + v.replace(" • ", "\n"))
            b.say(f"Contoh perintah {k}: " + ", ".join(v.split(" • ")[:3]) + ". Daftar lengkap ada di layar.")
            return
    b.app.log("sys", "\n\n".join(f"{k}:\n" + v.replace(" • ", "\n") for k, v in HELP.items()))
    b.say("Saya punya puluhan fitur. Kategorinya: " + ", ".join(HELP) +
          ". Katakan bantuan diikuti nama kategori, misalnya bantuan pengingat. Daftar lengkap ada di layar.")


# =========================================================
# PENGATURAN NOVA & PERCAKAPAN RINGAN
# =========================================================

@cmd(rx=r"^(ulangi|katakan lagi|ulangi lagi)$")
def h_repeat(b, c, m):
    if b.app.last_said:
        b.say(b.app.last_said)
    else:
        b.say("Belum ada yang bisa diulang.")


@cmd("bicara lebih cepat", "lebih cepat bicara", "bicara lebih lambat", "bicara lebih pelan", "bicara lebih lambat")
def h_rate(b, c, m):
    sp = b.app.speaker
    sp.rate = min(220, sp.rate + 25) if "cepat" in c else max(120, sp.rate - 25)
    b.say("Kecepatan bicara diubah.")


@cmd(rx=r"ganti suara(?: ke)? (ardi|gadis|laki|perempuan|wanita|pria)")
def h_voice(b, c, m):
    want = {"ardi": "ardi", "laki": "ardi", "pria": "ardi"}.get(m.group(1), "gadis")
    sp = b.app.speaker
    for label in sp.voices:
        if want in label.lower():
            sp.select(label)
            b.app.ui.put(("voice", label))
            b.say("Suara diganti.")
            return
    b.say("Suara itu tidak tersedia. Pasang edge-tts dan pygame untuk suara natural.")


@cmd("bersihkan chat", "hapus percakapan", "bersihkan percakapan")
def h_clear(b, c, m):
    b.app.ui.put(("clear",))
    b.say("Percakapan dibersihkan.")


@cmd(rx=r"(?:panggil (?:aku|saya)|namaku|nama saya)\s+([a-z ]+)")
def h_setname(b, c, m):
    d = load()
    d["name"] = m.group(1).strip().title()
    save(d)
    b.say(f"Baik, saya akan memanggilmu {d['name']}.")


@cmd("siapa namaku", "siapa nama saya")
def h_getname(b, c, m):
    n = load()["name"]
    b.say(f"Namamu {n}." if n else "Saya belum tahu namamu. Katakan panggil saya, diikuti namamu.")


@cmd("apa kabar")
def h_kabar(b, c, m):
    b.say(random.choice(["Baik. Terima kasih sudah bertanya. Kamu sendiri bagaimana?",
                         "Saya siap membantu. Ada yang bisa dikerjakan?"]))


@cmd(rx=r"^selamat (pagi|siang|sore|malam)")
def h_selamat(b, c, m):
    n = load()["name"]
    b.say(f"Selamat {m.group(1)}{', ' + n if n else ''}. Ada yang bisa saya bantu?")


@cmd("aku bosan", "saya bosan")
def h_bosan(b, c, m):
    random.choice([h_joke, h_fact, h_riddle, h_pantun])(b, c, m)


@cmd("siapa yang membuatmu", "siapa penciptamu", "siapa pembuatmu")
def h_creator(b, c, m):
    b.say("Kamu yang membuat saya, dan saya terus belajar fitur baru darimu.")


@cmd("ambil foto", "foto selfie", "potret aku")
def h_photo(b, c, m):
    import cv2
    cam = cv2.VideoCapture(0)
    ok, frame = cam.read()
    cam.release()
    if not ok:
        b.say("Kamera tidak bisa dipakai.")
        return
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    path = os.path.join(PHOTO_FOLDER, datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg"))
    cv2.imwrite(path, frame)
    b.app.log("sys", f"Tersimpan: {os.path.abspath(path)}")
    b.say("Foto berhasil diambil.")


# =========================================================
# WAKTU, TANGGAL, SALAT
# =========================================================

ZONES = {"tokyo": "Asia/Tokyo", "jepang": "Asia/Tokyo", "london": "Europe/London", "new york": "America/New_York",
         "los angeles": "America/Los_Angeles", "sydney": "Australia/Sydney", "dubai": "Asia/Dubai",
         "singapura": "Asia/Singapore", "singapore": "Asia/Singapore", "mekah": "Asia/Riyadh",
         "makkah": "Asia/Riyadh", "madinah": "Asia/Riyadh", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
         "seoul": "Asia/Seoul", "kuala lumpur": "Asia/Kuala_Lumpur", "jakarta": "Asia/Jakarta",
         "makassar": "Asia/Makassar", "jayapura": "Asia/Jayapura", "kairo": "Africa/Cairo", "moskow": "Europe/Moscow"}


@cmd(rx=r"jam berapa (?:sekarang )?di ([a-z ]+)")
def h_worldtime(b, c, m):
    place = m.group(1).strip()
    for name, zone in ZONES.items():
        if name in place:
            try:
                from zoneinfo import ZoneInfo
                t = datetime.datetime.now(ZoneInfo(zone))
            except Exception:
                b.say("Untuk fitur ini, pasang paket tzdata dengan pip install tzdata.")
                return
            b.say(f"Di {name.title()} sekarang pukul {t:%H.%M}.")
            return
    b.say("Saya belum mengenal kota itu.")


EVENTS = {"kemerdekaan": (8, 17), "tahun baru": (1, 1), "natal": (12, 25)}


@cmd(rx=r"berapa hari lagi (?:ke|sampai|menuju|untuk)?\s*(?:tanggal )?(.+)")
def h_countdown(b, c, m):
    target_txt = m.group(1).strip()
    today = datetime.date.today()
    target = None
    for name, (mo, d) in EVENTS.items():
        if name in target_txt:
            target = datetime.date(today.year, mo, d)
    mm = re.search(r"(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", target_txt)
    if mm and mm.group(2) in BULAN:
        target = datetime.date(int(mm.group(3) or today.year), BULAN.index(mm.group(2)) + 1, int(mm.group(1)))
    if not target:
        b.say("Sebutkan tanggalnya, misalnya berapa hari lagi ke 17 agustus.")
        return
    if target < today and not (mm and mm.group(3)):
        target = target.replace(year=target.year + 1)
    days = (target - today).days
    b.say("Itu hari ini." if days == 0 else f"{days} hari lagi." if days > 0 else f"Sudah lewat {-days} hari.")


PRAYERS = {"Fajr": "Subuh", "Dhuhr": "Zuhur", "Asr": "Asar", "Maghrib": "Magrib", "Isha": "Isya"}


@cmd("jadwal salat", "jadwal sholat", "salat berikutnya", "sholat berikutnya", "azan berikutnya",
     rx=r"\b(?:waktu|kapan|jam)\s+(?:salat |sholat )?(subuh|zuhur|dzuhur|asar|ashar|magrib|maghrib|isya)")
def h_prayer(b, c, m):
    mm = re.search(r"\bdi ([a-z ]+)$", c)
    city = mm.group(1).strip() if mm else DEFAULT_CITY
    url = f"https://api.aladhan.com/v1/timingsByCity?city={q(city)}&country={q(COUNTRY)}&method=20"
    t = http_json(url)["data"]["timings"]
    times = {PRAYERS[k]: t[k][:5] for k in PRAYERS}
    if "berikutnya" in c:
        now = datetime.datetime.now().strftime("%H:%M")
        nxt = next(((n, v) for n, v in times.items() if v > now), None)
        b.say(f"Salat berikutnya {nxt[0]} pukul {nxt[1].replace(':', '.')}." if nxt else
              f"Salat berikutnya Subuh besok pukul {times['Subuh'].replace(':', '.')}.")
        return
    if m:
        want = {"dzuhur": "zuhur", "ashar": "asar", "maghrib": "magrib"}.get(m.group(1), m.group(1)).title()
        b.say(f"{want} pukul {times[want].replace(':', '.')}.")
        return
    b.app.log("sys", f"Jadwal salat {city.title()}:\n" + "\n".join(f"{k}: {v}" for k, v in times.items()))
    b.say(f"Jadwal salat {city.title()}. " + ". ".join(f"{k} {v.replace(':', '.')}" for k, v in times.items()))


# =========================================================
# PENGINGAT, TIMER, ALARM, STOPWATCH, POMODORO
# =========================================================

TIMERS = {}
_seq = [0]


def schedule(b, seconds, message, every=None, label=None):
    _seq[0] += 1
    tid = _seq[0]

    def start(delay):
        t = threading.Timer(delay, fire)
        t.daemon = True
        TIMERS[tid] = {"label": label or message, "due": time.time() + delay, "timer": t, "every": every}
        t.start()

    def fire():
        if tid not in TIMERS:
            return
        beep()
        b.say(message)
        if every:
            start(every)
        else:
            TIMERS.pop(tid, None)

    start(seconds)
    return tid


def cancel_timers(prefix=None):
    n = 0
    for tid, t in list(TIMERS.items()):
        if prefix is None or t["label"].startswith(prefix):
            t["timer"].cancel()
            TIMERS.pop(tid, None)
            n += 1
    return n


def parse_duration(c):
    c = c.replace("setengah jam", "30 menit").replace("sejam", "1 jam").replace("semenit", "1 menit")
    return sum(int(n) * {"detik": 1, "menit": 60, "jam": 3600}[u]
               for n, u in re.findall(r"(\d+)\s*(detik|menit|jam)", c))


def dur_text(s):
    s = int(s)
    h, r = divmod(s, 3600)
    mi, sec = divmod(r, 60)
    return " ".join(p for p in (f"{h} jam" if h else "", f"{mi} menit" if mi else "",
                                f"{sec} detik" if sec and not h else "") if p) or "0 detik"


def parse_clock(c):
    m = re.search(r"jam\s*(\d{1,2})(?:[.:](\d{2}))?\s*(pagi|siang|sore|malam)?", c)
    if not m:
        return None
    h, mi, per = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if per in ("sore", "malam") and h < 12:
        h += 12
    elif per == "siang" and h < 11:
        h += 12
    return (h, mi) if h < 24 and mi < 60 else None


@cmd("daftar pengingat", "daftar timer", "daftar alarm", "timer apa saja", "pengingat apa saja")
def h_timers(b, c, m):
    if not TIMERS:
        b.say("Tidak ada pengingat aktif.")
        return
    lines = [f"{t['label']} - {dur_text(t['due'] - time.time())} lagi" for t in TIMERS.values()]
    b.app.log("sys", "\n".join(lines))
    b.say(f"Ada {len(lines)} pengingat aktif. " + ". ".join(lines[:3]))


@cmd(rx=r"batalkan (semua )?(pengingat|timer|alarm)|hentikan (timer|alarm)")
def h_cancel_timers(b, c, m):
    n = cancel_timers()
    b.say(f"{n} pengingat dibatalkan." if n else "Tidak ada pengingat aktif.")


@cmd(rx=r"\b(alarm|bangunkan)\b.*jam\s*\d")
def h_alarm(b, c, m):
    clock = parse_clock(c)
    if not clock:
        b.say("Saya tidak menangkap jam alarmnya.")
        return
    now = datetime.datetime.now()
    target = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    label = f"Alarm {target:%H.%M}"
    schedule(b, (target - now).total_seconds(), f"Alarm. Sekarang pukul {target:%H.%M}.", label=label)
    b.say(f"Alarm diatur pukul {target:%H.%M}, {dur_text((target - now).total_seconds())} lagi.")


@cmd(rx=r"\b(timer|ingatkan|pengingat|hitung mundur)\b")
def h_timer(b, c, m):
    secs = parse_duration(c)
    if not secs:
        return False
    every = bool(re.search(r"\b(setiap|tiap)\b", c))
    msg = re.sub(r"\b(ingatkan|pengingat|timer|hitung mundur|tolong|saya|aku|kami|untuk|dalam|lagi|setiap|tiap|selama|"
                 r"\d+\s*(detik|menit|jam)|setengah jam|sejam|semenit)\b", " ", c)
    msg = re.sub(r"\s+", " ", msg).strip()
    text = f"Pengingat: {msg}." if msg else "Timer selesai."
    schedule(b, secs, text, every=secs if every else None, label=msg or f"Timer {dur_text(secs)}")
    if msg:
        b.say(f"Baik. Saya akan mengingatkan {msg} " + (f"setiap {dur_text(secs)}." if every else f"{dur_text(secs)} lagi."))
    else:
        b.say(f"Pengingat setiap {dur_text(secs)} dimulai." if every else f"Timer {dur_text(secs)} dimulai.")


_stopwatch = {"t": None}


@cmd("mulai stopwatch", "stopwatch mulai")
def h_sw_start(b, c, m):
    _stopwatch["t"] = time.time()
    b.say("Stopwatch dimulai.")


@cmd("berhenti stopwatch", "hentikan stopwatch", "cek stopwatch", "waktu stopwatch", "stopwatch berapa")
def h_sw_stop(b, c, m):
    if _stopwatch["t"] is None:
        b.say("Stopwatch belum dimulai.")
        return
    el = time.time() - _stopwatch["t"]
    if "cek" not in c and "berapa" not in c and "waktu" not in c:
        _stopwatch["t"] = None
    b.say(f"Waktu stopwatch {dur_text(el)}.")


@cmd("pomodoro")
def h_pomodoro(b, c, m):
    if re.search(r"hentikan|batalkan|berhenti", c):
        b.say(f"Pomodoro dihentikan." if cancel_timers("Pomodoro") else "Tidak ada pomodoro aktif.")
        return
    mm = re.search(r"(\d+)\s*menit", c)
    focus, rest, rounds, t = int(mm.group(1)) if mm else 25, 5, 4, 0
    for r in range(rounds):
        t += focus * 60
        last = r == rounds - 1
        schedule(b, t, "Semua sesi pomodoro selesai. Kerja bagus." if last else
                 f"Sesi fokus {r + 1} selesai. Istirahat {rest} menit.", label=f"Pomodoro fokus {r + 1}")
        if not last:
            t += rest * 60
            schedule(b, t, f"Istirahat selesai. Mulai sesi fokus {r + 2}.", label=f"Pomodoro istirahat {r + 1}")
    b.say(f"Pomodoro dimulai: {rounds} sesi fokus {focus} menit dengan istirahat {rest} menit.")


# =========================================================
# PRODUKTIVITAS: TUGAS, AGENDA, DIKTE
# =========================================================

@cmd(rx=r"\b(?:tambah|tambahkan|buat) tugas (.+)")
def h_task_add(b, c, m):
    d = load()
    d["tasks"].append({"text": m.group(1).strip(), "done": False})
    save(d)
    b.say(f"Tugas ditambahkan. Sekarang ada {len(d['tasks'])} tugas.")


@cmd("daftar tugas", "tugas saya", "apa saja tugas", "tugas apa saja")
def h_task_list(b, c, m):
    tasks = load()["tasks"]
    if not tasks:
        b.say("Daftar tugas kosong.")
        return
    lines = [f"{i}. [{'x' if t['done'] else ' '}] {t['text']}" for i, t in enumerate(tasks, 1)]
    b.app.log("sys", "\n".join(lines))
    todo = [f"nomor {i}, {t['text']}" for i, t in enumerate(tasks, 1) if not t["done"]]
    b.say(f"Ada {len(todo)} tugas belum selesai. " + ". ".join(todo[:5]) if todo else "Semua tugas sudah selesai.")


@cmd(rx=r"(?:selesaikan|centang|tandai) tugas (?:nomor )?(\d+)|tugas (?:nomor )?(\d+) (?:sudah )?selesai")
def h_task_done(b, c, m):
    n = int(m.group(1) or m.group(2))
    d = load()
    if not 1 <= n <= len(d["tasks"]):
        b.say("Nomor tugas tidak ada.")
        return
    d["tasks"][n - 1]["done"] = True
    save(d)
    b.say(f"Tugas nomor {n} selesai.")


@cmd(rx=r"hapus tugas (?:nomor )?(\d+)")
def h_task_del(b, c, m):
    n = int(m.group(1))
    d = load()
    if not 1 <= n <= len(d["tasks"]):
        b.say("Nomor tugas tidak ada.")
        return
    removed = d["tasks"].pop(n - 1)
    save(d)
    b.say(f"Tugas {removed['text']} dihapus.")


@cmd("hapus semua tugas")
def h_task_clear(b, c, m):
    def go():
        d = load()
        d["tasks"] = []
        save(d)
        b.say("Semua tugas dihapus.")
    ask(b, "Hapus semua tugas?", go)


def parse_date(c):
    today = datetime.date.today()
    if "lusa" in c:
        return today + datetime.timedelta(days=2)
    if "besok" in c:
        return today + datetime.timedelta(days=1)
    mm = re.search(r"tanggal\s*(\d{1,2})\s*([a-z]+)?", c)
    if mm:
        month = BULAN.index(mm.group(2)) + 1 if mm.group(2) in BULAN else today.month
        try:
            return datetime.date(today.year, month, int(mm.group(1)))
        except ValueError:
            pass
    return today


@cmd(rx=r"\b(?:tambah|tambahkan|buat) agenda (.+)")
def h_agenda_add(b, c, m):
    body = m.group(1)
    date = parse_date(body)
    clock = parse_clock(body)
    text = re.sub(r"\b(hari ini|besok|lusa|tanggal\s*\d{1,2}(\s+[a-z]+)?|jam\s*\d{1,2}([.:]\d{2})?\s*(pagi|siang|sore|malam)?)\b",
                  " ", body)
    text = re.sub(r"\s+", " ", text).strip() or "Agenda"
    d = load()
    d["agenda"].append({"date": date.isoformat(), "time": f"{clock[0]:02d}:{clock[1]:02d}" if clock else "",
                        "text": text})
    save(d)
    when = f"{date.day} {BULAN[date.month - 1]}" + (f" pukul {clock[0]:02d}.{clock[1]:02d}" if clock else "")
    if clock:
        due = datetime.datetime.combine(date, datetime.time(*clock)) - datetime.timedelta(minutes=10)
        if due > datetime.datetime.now():
            schedule(b, (due - datetime.datetime.now()).total_seconds(),
                     f"Sepuluh menit lagi: {text}.", label=f"Agenda {text}")
    b.say(f"Agenda {text} disimpan untuk {when}.")


@cmd(rx=r"agenda (hari ini|besok|lusa|minggu ini|semua)|(?:apa|ada) agenda")
def h_agenda_show(b, c, m):
    today = datetime.date.today()
    key = m.group(1) if m and m.group(1) else "hari ini"
    items = load()["agenda"]
    if key == "minggu ini":
        end = today + datetime.timedelta(days=7)
        sel = [a for a in items if today.isoformat() <= a["date"] <= end.isoformat()]
    elif key == "semua":
        sel = [a for a in items if a["date"] >= today.isoformat()]
    else:
        day = today + datetime.timedelta(days={"hari ini": 0, "besok": 1, "lusa": 2}[key])
        sel = [a for a in items if a["date"] == day.isoformat()]
    sel.sort(key=lambda a: (a["date"], a["time"]))
    if not sel:
        b.say(f"Tidak ada agenda untuk {key}.")
        return
    b.app.log("sys", "\n".join(f"{a['date']} {a['time']} {a['text']}" for a in sel))
    b.say(f"Ada {len(sel)} agenda. " + ". ".join(
        (f"pukul {a['time'].replace(':', '.')} " if a["time"] else "") + a["text"] for a in sel[:5]))


@cmd("mulai mendikte", "mode dikte", "mulai dikte")
def h_dictate_start(b, c, m):
    b.mode = "dictation"
    b.say("Mode dikte aktif. Arahkan kursor ke tempat mengetik. Katakan selesai mendikte untuk berhenti.")


def paste(text):
    set_clipboard(text)
    time.sleep(0.15)
    keys("ctrl", "v")
    time.sleep(0.15)


def dictate(b, c):
    if re.search(r"(selesai|akhiri|hentikan|berhenti)\s+(mendikte|dikte)", c):
        b.mode = None
        b.say("Mode dikte selesai.")
        return True
    text = c
    for word, sym in [("tanda tanya", "?"), ("tanda seru", "!"), ("titik dua", ":"), ("koma", ","), ("titik", ".")]:
        text = re.sub(rf"\s*\b{word}\b", sym, text)
    text = re.sub(r"\s*\bparagraf baru\b\s*", "\n\n", text)
    text = re.sub(r"\s*\bbaris baru\b\s*", "\n", text)
    parts = text.split("\n")
    for i, part in enumerate(parts):
        if part.strip():
            paste(part.strip()[0].upper() + part.strip()[1:] + " ")
        if i < len(parts) - 1:
            keys("enter")
    return True


@cmd(rx=r"^ketik (.+)")
def h_type(b, c, m):
    paste(m.group(1))
    b.app.log("sys", "Diketik ke jendela aktif.")


@cmd("hapus catatan")
def h_notes_del(b, c, m):
    def go():
        if os.path.exists("nova_catatan.txt"):
            os.remove("nova_catatan.txt")
        b.say("Semua catatan dihapus.")
    ask(b, "Hapus semua catatan?", go)


# =========================================================
# INTERNET: CUACA, WIKIPEDIA, BERITA, KURS, TERJEMAH
# =========================================================

WCODE = {0: "cerah", 1: "cerah berawan", 2: "berawan sebagian", 3: "berawan", 45: "berkabut", 48: "berkabut",
         51: "gerimis ringan", 53: "gerimis", 55: "gerimis lebat", 61: "hujan ringan", 63: "hujan",
         65: "hujan lebat", 71: "salju ringan", 73: "salju", 75: "salju lebat", 80: "hujan sesaat",
         81: "hujan sesaat lebat", 82: "hujan sangat lebat", 95: "badai petir", 96: "badai petir",
         99: "badai petir dan hujan es"}


@cmd("cuaca", "akan hujan", "hujan tidak")
def h_weather(b, c, m):
    mm = re.search(r"\bdi ([a-z ]+)", c)
    city = re.sub(r"\b(hari ini|besok|sekarang|nanti|ya|lusa)\b", "", mm.group(1)).strip() if mm else ""
    city = city or DEFAULT_CITY
    geo = http_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=id&name=" + q(city))
    if not geo.get("results"):
        b.say("Kota itu tidak ditemukan.")
        return
    g = geo["results"][0]
    w = http_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto&forecast_days=2"
                  "&current=temperature_2m,relative_humidity_2m,weather_code"
                  "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                  % (g["latitude"], g["longitude"]))
    day = 1 if "besok" in c else 0
    dl = w["daily"]
    rain = dl["precipitation_probability_max"][day]
    span = f"suhu {round(dl['temperature_2m_min'][day])} sampai {round(dl['temperature_2m_max'][day])} derajat, " \
           f"peluang hujan {rain} persen"
    if "hujan" in c and "cuaca" not in c:
        b.say(f"Peluang hujan {'besok' if day else 'hari ini'} di {g['name']} sekitar {rain} persen.")
    elif day:
        b.say(f"Besok di {g['name']} {WCODE.get(dl['weather_code'][1], 'berubah-ubah')}, {span}.")
    else:
        cur = w["current"]
        b.say(f"Cuaca di {g['name']} sekarang {WCODE.get(cur['weather_code'], 'berubah-ubah')}, "
              f"{round(cur['temperature_2m'])} derajat, kelembapan {cur['relative_humidity_2m']} persen. "
              f"Hari ini {span}.")


@cmd("apa itu", "siapa itu", "wikipedia", "jelaskan tentang", "ceritakan tentang")
def h_wiki(b, c, m):
    topic = re.split(r"apa itu|siapa itu|wikipedia|jelaskan tentang|ceritakan tentang", c, 1)[-1]
    topic = re.sub(r"^\s*(di|tentang|cari|cari di)\s+", "", topic).strip()
    if not topic:
        if "buka" in c:
            return False
        b.say("Apa yang ingin kamu ketahui?")
        return
    res = http_json("https://id.wikipedia.org/w/rest.php/v1/search/page?limit=1&q=" + q(topic)).get("pages") or []
    if not res:
        b.say("Saya tidak menemukannya di Wikipedia.")
        return
    page = http_json("https://id.wikipedia.org/api/rest_v1/page/summary/" + q(res[0]["key"]))
    text = page.get("extract", "")
    b.app.log("sys", f"{page.get('title', topic)}: {text}")
    b.say(" ".join(re.split(r"(?<=[.!?])\s+", text)[:2]) or "Tidak ada ringkasan.")


@cmd("berita")
def h_news(b, c, m):
    topic = re.sub(r"\b(berita|terbaru|terkini|tentang|hari ini|apa|ada|yang|dong|ya)\b", " ", c)
    topic = re.sub(r"\s+", " ", topic).strip()
    base = "https://news.google.com/rss"
    url = (f"{base}/search?q={q(topic)}&" if topic else f"{base}?") + "hl=id&gl=ID&ceid=ID:id"
    root = ET.fromstring(http_get(url))
    titles = [i.findtext("title") for i in root.iter("item")][:5]
    if not titles:
        b.say("Tidak ada berita yang ditemukan.")
        return
    b.app.log("sys", "\n".join(f"{n}. {t}" for n, t in enumerate(titles, 1)))
    b.say("Berita teratas. " + ". ".join(re.sub(r"\s+-\s+[^-]+$", "", t) for t in titles[:4]))


CUR = [("dolar singapura", "SGD"), ("dolar australia", "AUD"), ("dolar amerika", "USD"), ("dolar", "USD"),
       ("euro", "EUR"), ("yen", "JPY"), ("ringgit", "MYR"), ("poundsterling", "GBP"), ("pound", "GBP"),
       ("riyal", "SAR"), ("won", "KRW"), ("yuan", "CNY"), ("baht", "THB"), ("rupiah", "IDR")]
CUR_NAME = {}
for _n, _c in CUR:
    CUR_NAME.setdefault(_c, _n)


def find_cur(text):
    found = []
    for name, code in CUR:
        i = text.find(name)
        if i >= 0:
            found.append((i, code))
            text = text[:i] + " " * len(name) + text[i + len(name):]
    return [code for _, code in sorted(found)]


@cmd("kurs", rx=r"\d+\s*(?:dolar|euro|yen|ringgit|pound|riyal|won|yuan|baht)")
def h_kurs(b, c, m):
    codes = find_cur(c)
    if not codes:
        return False
    amount = num(re.search(r"\d+(?:[.,]\d+)?", c).group()) if re.search(r"\d", c) else 1
    src = codes[0]
    dst = codes[1] if len(codes) > 1 else ("IDR" if src != "IDR" else "USD")
    rate = http_json(f"https://open.er-api.com/v6/latest/{src}")["rates"][dst]
    b.say(f"{fmt(amount)} {CUR_NAME[src]} sama dengan {fmt(amount * rate)} {CUR_NAME[dst]}.")


LANGS = {"inggris": "en", "arab": "ar", "jepang": "ja", "korea": "ko", "mandarin": "zh-CN", "prancis": "fr",
         "jerman": "de", "spanyol": "es", "melayu": "ms", "belanda": "nl", "rusia": "ru", "turki": "tr",
         "indonesia": "id"}


@cmd(rx=r"terjemahkan (.+?) ke (?:bahasa )?([a-z]+)")
def h_translate(b, c, m):
    text, lang = m.group(1), m.group(2)
    if lang not in LANGS:
        b.say("Bahasa itu belum saya kenal.")
        return
    src = "en" if lang == "indonesia" else "id"
    j = http_json(f"https://api.mymemory.translated.net/get?q={q(text)}&langpair={src}|{LANGS[lang]}")
    out = j["responseData"]["translatedText"]
    b.app.log("sys", f"{text} -> {out}")
    b.say(f"Dalam bahasa {lang}: {out}")


@cmd("cek internet", "tes internet", "tes koneksi", "koneksi internet")
def h_net(b, c, m):
    try:
        t = time.time()
        http_get("https://www.google.com/generate_204", 5)
        b.say(f"Internet terhubung. Respon {int((time.time() - t) * 1000)} milidetik.")
    except OSError:
        b.say("Internet tidak terhubung.")


@cmd("ip address", "alamat ip")
def h_ip(b, c, m):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local = s.getsockname()[0]
    finally:
        s.close()
    try:
        public = http_get("https://api.ipify.org", 5).decode()
    except OSError:
        public = "tidak diketahui"
    b.app.log("sys", f"IP lokal: {local}\nIP publik: {public}")
    b.say(f"IP lokal kamu {local}. IP publik {public}. Rinciannya ada di layar.")


@cmd("nama wifi", "wifi apa")
def h_wifi(b, c, m):
    out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                         creationflags=NOWIN).stdout
    mm = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
    b.say(f"Terhubung ke Wi-Fi {mm.group(1).strip()}." if mm else "Tidak sedang terhubung ke Wi-Fi.")


# =========================================================
# HITUNG & KONVERSI
# =========================================================

UNITS = {
    "panjang": {"km": 1000, "kilometer": 1000, "meter": 1, "m": 1, "cm": .01, "sentimeter": .01, "mm": .001,
                "milimeter": .001, "mil": 1609.344, "kaki": .3048, "inci": .0254, "yard": .9144},
    "berat": {"kg": 1, "kilogram": 1, "gram": .001, "g": .001, "ons": .1, "pon": .45359237, "lb": .45359237,
              "ton": 1000},
    "volume": {"liter": 1, "l": 1, "ml": .001, "mililiter": .001, "galon": 3.78541},
}
TEMPS = ("celsius", "fahrenheit", "kelvin")


@cmd(rx=r"(\d+(?:[.,]\d+)?)\s*(?:derajat\s*)?([a-z]+)\s+(?:ke|jadi|menjadi|dalam)\s+(?:berapa\s+)?([a-z]+)")
def h_convert(b, c, m):
    val, u1, u2 = num(m.group(1)), m.group(2), m.group(3)
    if u1 in TEMPS and u2 in TEMPS:
        k = val if u1 == "kelvin" else val + 273.15 if u1 == "celsius" else (val - 32) * 5 / 9 + 273.15
        out = k if u2 == "kelvin" else k - 273.15 if u2 == "celsius" else (k - 273.15) * 9 / 5 + 32
        b.say(f"{fmt(val)} {u1} sama dengan {fmt(round(out, 2))} {u2}.")
        return
    for table in UNITS.values():
        if u1 in table and u2 in table:
            b.say(f"{fmt(val)} {u1} sama dengan {fmt(round(val * table[u1] / table[u2], 4))} {u2}.")
            return
    return False


@cmd(rx=r"([\d.,]+)\s*persen dari\s*([\d.,]+)")
def h_percent(b, c, m):
    b.say(f"Hasilnya {fmt(round(num(m.group(1)) / 100 * num(m.group(2)), 4))}.")


@cmd(rx=r"akar (?:kuadrat )?(?:dari )?(\d+(?:[.,]\d+)?)")
def h_sqrt(b, c, m):
    b.say(f"Akarnya {fmt(round(math.sqrt(num(m.group(1))), 4))}.")


@cmd(rx=r"(\d+(?:[.,]\d+)?)\s*pangkat\s*(\d+)")
def h_power(b, c, m):
    if int(m.group(2)) > 100:
        b.say("Pangkatnya terlalu besar.")
        return
    b.say(f"Hasilnya {fmt(round(num(m.group(1)) ** int(m.group(2)), 4))}.")


# =========================================================
# KOMPUTER & SISTEM
# =========================================================

@cmd("info sistem", "penggunaan cpu", "penggunaan ram", "penggunaan memori", "sisa penyimpanan", "sisa disk",
     "kapasitas disk", "lama komputer menyala")
def h_sys(b, c, m):
    if not psutil:
        b.say("Pasang paket psutil dengan pip install psutil.")
        return
    cpu = psutil.cpu_percent(interval=0.6)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    up = dur_text(time.time() - psutil.boot_time())
    parts = {"cpu": f"CPU terpakai {cpu:.0f} persen",
             "ram": f"RAM terpakai {ram.percent:.0f} persen dari {ram.total / 1e9:.0f} gigabyte",
             "disk": f"penyimpanan tersisa {disk.free / 1e9:.0f} gigabyte dari {disk.total / 1e9:.0f}",
             "menyala": f"komputer menyala selama {up}"}
    for key in ("cpu", "ram", "memori", "disk", "penyimpanan", "menyala"):
        if key in c:
            b.say(parts.get({"memori": "ram", "penyimpanan": "disk"}.get(key, key)) + ".")
            return
    b.app.log("sys", "\n".join(parts.values()))
    b.say(". ".join(parts.values()) + ".")


@cmd("aplikasi yang berjalan", "aplikasi apa yang berjalan", "proses terberat")
def h_procs(b, c, m):
    if not psutil:
        b.say("Pasang paket psutil dengan pip install psutil.")
        return
    mem = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            mem[p.info["name"]] = mem.get(p.info["name"], 0) + p.info["memory_info"].rss
        except Exception:
            pass
    top = sorted(mem.items(), key=lambda x: -x[1])[:5]
    b.app.log("sys", "\n".join(f"{n}: {v / 1e6:.0f} MB" for n, v in top))
    b.say("Lima aplikasi terberat: " + ", ".join(n.replace(".exe", "") for n, _ in top) + ".")


@cmd(rx=r"volume\D{0,12}(\d{1,3})\b")
def h_volume_set(b, c, m):
    pct = max(0, min(100, int(m.group(1))))
    keys_n = lambda k, n: pyautogui.press(k, presses=n)
    keys_n("volumedown", 50)
    keys_n("volumeup", pct // 2)
    b.say(f"Volume diatur sekitar {pct} persen.")


@cmd(rx=r"(?:kecerahan|brightness)\D{0,12}(\d{1,3})\b")
def h_brightness(b, c, m):
    pct = max(0, min(100, int(m.group(1))))
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                    f".WmiSetBrightness(1,{pct})"], creationflags=NOWIN, capture_output=True)
    b.say(f"Kecerahan layar diatur {pct} persen.")


@cmd("mode gelap", "tema gelap", "mode terang", "tema terang")
def h_theme(b, c, m):
    val = "0" if "gelap" in c else "1"
    for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
        subprocess.run(["reg", "add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                        "/v", name, "/t", "REG_DWORD", "/d", val, "/f"], creationflags=NOWIN, capture_output=True)
    b.say("Tema gelap diaktifkan." if val == "0" else "Tema terang diaktifkan.")


def _power(b, question, args, done):
    def go():
        subprocess.Popen(args, creationflags=NOWIN)
        b.say(done)
    ask(b, question, go)


@cmd("matikan komputer", "matikan laptop", "matikan pc", "shutdown komputer")
def h_shutdown(b, c, m):
    _power(b, "Yakin ingin mematikan komputer?", ["shutdown", "/s", "/t", "30"],
           "Komputer akan mati dalam 30 detik. Katakan batalkan shutdown untuk membatalkan.")


@cmd("restart komputer", "restart laptop", "mulai ulang komputer")
def h_restart(b, c, m):
    _power(b, "Yakin ingin me-restart komputer?", ["shutdown", "/r", "/t", "30"],
           "Komputer akan restart dalam 30 detik. Katakan batalkan shutdown untuk membatalkan.")


@cmd("batalkan shutdown", "batalkan restart", "batalkan mematikan")
def h_shutdown_cancel(b, c, m):
    subprocess.run(["shutdown", "/a"], creationflags=NOWIN, capture_output=True)
    b.say("Pembatalan dikirim.")


@cmd("tidurkan komputer", "tidurkan laptop", "mode tidur")
def h_sleep(b, c, m):
    _power(b, "Tidurkan komputer sekarang?", ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
           "Komputer ditidurkan.")


@cmd("keluar dari windows", "log off", "sign out")
def h_logoff(b, c, m):
    _power(b, "Keluar dari akun Windows?", ["shutdown", "/l"], "Keluar dari akun.")


@cmd("kosongkan recycle bin", "kosongkan tong sampah")
def h_recycle(b, c, m):
    def go():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                       creationflags=NOWIN, capture_output=True)
        b.say("Recycle Bin dikosongkan.")
    ask(b, "Kosongkan Recycle Bin? Ini tidak bisa dibatalkan.", go)


APP_EXE = {"chrome": "chrome.exe", "edge": "msedge.exe", "notepad": "notepad.exe", "spotify": "spotify.exe",
           "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe", "whatsapp": "whatsapp.exe",
           "discord": "discord.exe", "vlc": "vlc.exe", "telegram": "telegram.exe", "paint": "mspaint.exe"}


@cmd(rx=r"tutup aplikasi ([a-z0-9 ]+)")
def h_kill(b, c, m):
    name = m.group(1).strip()
    exe = APP_EXE.get(name, name.replace(" ", "") + ".exe")

    def go():
        r = subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, creationflags=NOWIN)
        b.say(f"{name} ditutup." if r.returncode == 0 else f"{name} tidak sedang berjalan.")
    ask(b, f"Tutup paksa {name}? Pekerjaan yang belum disimpan bisa hilang.", go)


# =========================================================
# JENDELA, PINTASAN KEYBOARD, MEDIA, CLIPBOARD
# =========================================================

@cmd("bacakan clipboard", "baca clipboard", "baca teks yang disalin", "apa isi clipboard")
def h_clip_read(b, c, m):
    t = get_clipboard()
    b.say(t[:400] if t else "Clipboard kosong.")


@cmd("hapus clipboard", "bersihkan clipboard")
def h_clip_clear(b, c, m):
    set_clipboard("")
    b.say("Clipboard dibersihkan.")


@cmd(rx=r"^salin (?:teks |kalimat )(.+)")
def h_clip_set(b, c, m):
    set_clipboard(m.group(1))
    b.say("Teks disalin ke clipboard.")


@cmd("tutup jendela")
def h_close_window(b, c, m):
    ask(b, "Tutup jendela yang sedang aktif?", lambda: (keys("alt", "f4"), b.say("Jendela ditutup.")))


@cmd("putar musik", "jeda musik", "lanjutkan musik", "hentikan musik", "pause musik", "lagu berikutnya",
     "lagu selanjutnya", "lagu sebelumnya", rx=r"\bputar lagu\b|\bputar musik\b")
def h_media(b, c, m):
    mm = re.search(r"putar (?:lagu|musik) (.+)", c)
    if mm and not re.search(r"berikutnya|sebelumnya|selanjutnya", mm.group(1)):
        webbrowser.open("https://www.youtube.com/results?search_query=" + q(mm.group(1)))
        b.say(f"Mencari lagu {mm.group(1)} di YouTube.")
    elif "berikutnya" in c or "selanjutnya" in c:
        keys("nexttrack")
        b.say("Lagu berikutnya.")
    elif "sebelumnya" in c:
        keys("prevtrack")
        b.say("Lagu sebelumnya.")
    else:
        keys("playpause")
        b.say("Oke.")


KEYMAP = {"enter": "enter", "spasi": "space", "escape": "esc", "esc": "esc", "tab": "tab", "hapus": "backspace",
          "backspace": "backspace", "panah atas": "up", "panah bawah": "down", "panah kiri": "left",
          "panah kanan": "right", "home": "home", "end": "end"}


@cmd(rx=r"^tekan (enter|spasi|escape|esc|tab|hapus|backspace|panah atas|panah bawah|panah kiri|panah kanan|home|end)")
def h_press(b, c, m):
    keys(KEYMAP[m.group(1)])
    b.app.log("sys", f"Menekan {m.group(1)}.")


KEYS = [
    (r"tampilkan desktop|minimalkan semua", ("win", "d"), "Desktop ditampilkan."),
    (r"ganti jendela|pindah jendela|ganti aplikasi", ("alt", "tab"), "Berpindah jendela."),
    (r"buka kembali tab|tab yang tertutup", ("ctrl", "shift", "t"), "Tab dibuka kembali."),
    (r"tab baru", ("ctrl", "t"), "Tab baru dibuka."),
    (r"tutup tab", ("ctrl", "w"), "Tab ditutup."),
    (r"tab berikutnya", ("ctrl", "tab"), "Tab berikutnya."),
    (r"tab sebelumnya", ("ctrl", "shift", "tab"), "Tab sebelumnya."),
    (r"\b(refresh|muat ulang|segarkan)\b", ("f5",), "Halaman dimuat ulang."),
    (r"layar penuh", ("f11",), "Mode layar penuh."),
    (r"\b(perbesar|zoom in)\b", ("ctrl", "="), "Diperbesar."),
    (r"\b(perkecil|zoom out)\b", ("ctrl", "-"), "Diperkecil."),
    (r"\bsalin\b", ("ctrl", "c"), "Disalin."),
    (r"\btempel\b", ("ctrl", "v"), "Ditempel."),
    (r"potong layar|tangkap area|snipping", ("win", "shift", "s"), "Pilih area layar."),
    (r"\bpotong\b", ("ctrl", "x"), "Dipotong."),
    (r"pilih semua", ("ctrl", "a"), "Semua dipilih."),
    (r"\b(urungkan|undo)\b", ("ctrl", "z"), "Diurungkan."),
    (r"\bredo\b|ulangi aksi", ("ctrl", "y"), "Diulang."),
    (r"simpan (file|dokumen)", ("ctrl", "s"), "Menyimpan."),
    (r"cari di halaman", ("ctrl", "f"), "Kolom pencarian dibuka."),
    (r"pengelola tugas", ("ctrl", "shift", "esc"), "Membuka Task Manager."),
    (r"tampilan tugas", ("win", "tab"), "Tampilan tugas dibuka."),
    (r"rekam layar", ("win", "alt", "r"), "Merekam layar dengan Game Bar."),
    (r"panel emoji|buka emoji", ("win", "."), "Panel emoji dibuka."),
    (r"riwayat clipboard", ("win", "v"), "Riwayat clipboard dibuka."),
    (r"halaman berikutnya", ("pagedown",), "Halaman berikutnya."),
    (r"halaman sebelumnya", ("pageup",), "Halaman sebelumnya."),
    (r"paling atas|ke awal halaman", ("ctrl", "home"), "Ke bagian atas."),
    (r"paling bawah|ke akhir halaman", ("ctrl", "end"), "Ke bagian bawah."),
    (r"gulir ke bawah|scroll ke bawah", ("scroll", -700), "Menggulir ke bawah."),
    (r"gulir ke atas|scroll ke atas", ("scroll", 700), "Menggulir ke atas."),
]
_KEYS_RX = "|".join(f"(?:{p})" for p, _, _ in KEYS)


@cmd(rx=_KEYS_RX)
def h_keys(b, c, m):
    for pattern, action, reply in KEYS:
        if re.search(pattern, c):
            if action[0] == "scroll":
                pyautogui.scroll(action[1])
            else:
                keys(*action)
            b.app.log("sys", reply)
            return
    return False


# =========================================================
# FILE & FOLDER
# =========================================================

def user_dirs():
    h = os.path.expanduser("~")
    return [p for p in (os.path.join(h, d) for d in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"))
            if os.path.isdir(p)]


@cmd("cari file", "temukan file", "cari dokumen")
def h_findfile(b, c, m):
    words = re.sub(r"^.*?(cari file|temukan file|cari dokumen)\s*", "", c).split()
    if not words:
        b.say("File apa yang ingin dicari? Contoh: cari file laporan.")
        return
    found, scanned = [], 0
    for root in user_dirs():
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith(".") and d.lower() not in ("node_modules", "__pycache__")]
            for f in fn:
                scanned += 1
                if all(w in f.lower() for w in words):
                    found.append(os.path.join(dp, f))
            if len(found) >= 8 or scanned > 60000:
                break
        if len(found) >= 8 or scanned > 60000:
            break
    b.last_files = found
    if not found:
        b.say("File itu tidak ditemukan.")
        return
    b.app.log("sys", "\n".join(f"{i}. {p}" for i, p in enumerate(found, 1)))
    b.say(f"Ketemu {len(found)} file. Yang pertama {os.path.basename(found[0])}. "
          "Katakan buka file pertama untuk membukanya.")


ORD = {"pertama": 1, "kedua": 2, "ketiga": 3, "keempat": 4, "kelima": 5}


@cmd(rx=r"buka (?:file|hasil)\s*(?:nomor\s*)?(pertama|kedua|ketiga|keempat|kelima|\d)")
def h_openfile(b, c, m):
    n = ORD.get(m.group(1)) or int(m.group(1))
    if not b.last_files or not 1 <= n <= len(b.last_files):
        b.say("Belum ada hasil pencarian file.")
        return
    os.startfile(b.last_files[n - 1])
    b.say("Membuka file.")


@cmd("file terbaru", "unduhan terbaru", "download terbaru")
def h_newest(b, c, m):
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.isfile(os.path.join(folder, f)) and not f.endswith((".crdownload", ".tmp", ".part"))]
    if not files:
        b.say("Folder Downloads kosong.")
        return
    newest = max(files, key=os.path.getmtime)
    if "buka" in c:
        os.startfile(newest)
        b.say("Membuka file terbaru.")
    else:
        b.say(f"File terbaru di Downloads adalah {os.path.basename(newest)}.")


CATS = {"Gambar": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"),
        "Dokumen": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"),
        "Video": (".mp4", ".mkv", ".avi", ".mov"),
        "Musik": (".mp3", ".wav", ".flac", ".m4a"),
        "Arsip": (".zip", ".rar", ".7z", ".tar", ".gz"),
        "Program": (".exe", ".msi")}


@cmd("rapikan downloads", "rapikan unduhan", "rapikan folder download")
def h_organize(b, c, m):
    folder = os.path.join(os.path.expanduser("~"), "Downloads")

    def go():
        moved = 0
        for f in os.listdir(folder):
            src = os.path.join(folder, f)
            if not os.path.isfile(src) or f.endswith((".crdownload", ".tmp", ".part")):
                continue
            ext = os.path.splitext(f)[1].lower()
            cat = next((k for k, v in CATS.items() if ext in v), "Lainnya")
            dest_dir = os.path.join(folder, cat)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, f)
            i = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{os.path.splitext(f)[0]}_{i}{ext}")
                i += 1
            try:
                shutil.move(src, dest)
                moved += 1
            except Exception:
                pass
        b.say(f"{moved} file dirapikan ke folder berdasarkan jenisnya.")
    ask(b, "File di Downloads akan dipindah ke subfolder menurut jenisnya. Lanjutkan?", go)


@cmd(rx=r"buat folder (.+)")
def h_mkdir(b, c, m):
    name = re.sub(r'[\\/:*?"<>|]', "", m.group(1)).strip().title()
    if not name:
        b.say("Sebutkan nama foldernya.")
        return
    os.makedirs(os.path.join(os.path.expanduser("~"), "Desktop", name), exist_ok=True)
    b.say(f"Folder {name} dibuat di Desktop.")


@cmd(rx=r"jumlah file di (downloads|download|documents|dokumen|desktop|pictures|gambar)")
def h_count(b, c, m):
    name = {"download": "Downloads", "dokumen": "Documents", "gambar": "Pictures"}.get(m.group(1), m.group(1).title())
    path = os.path.join(os.path.expanduser("~"), name)
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    size = sum(os.path.getsize(os.path.join(path, f)) for f in files) / 1e6
    b.say(f"Ada {len(files)} file di {name}, total {size:.0f} megabyte.")


# =========================================================
# APLIKASI, WEBSITE, PENCARIAN, PESAN
# =========================================================

EXTRA_APPS = {"word": "winword", "excel": "excel", "powerpoint": "powerpnt", "spotify": "spotify:",
              "whatsapp": "whatsapp:", "kamera": "microsoft.windows.camera:", "vs code": "code",
              "vscode": "code", "visual studio code": "code", "microsoft store": "ms-windows-store:",
              "kalender": "outlookcal:", "peta": "bingmaps:", "snipping tool": "ms-screenclip:",
              "discord": "discord:", "telegram": "tg:", "vlc": "vlc", "steam": "steam:", "zoom": "zoommtg:",
              "teams": "msteams:", "onenote": "onenote:", "outlook": "outlook"}


@cmd(rx=r"\b(?:buka|jalankan|nyalakan)\b.*\b(" + "|".join(re.escape(k) for k in sorted(EXTRA_APPS, key=len, reverse=True)) + r")\b")
def h_more_apps(b, c, m):
    b.say(f"Membuka {m.group(1)}.")
    start_proc(EXTRA_APPS[m.group(1)])


EXTRA_SITES = {"google drive": "https://drive.google.com", "google docs": "https://docs.google.com",
               "google sheets": "https://sheets.google.com", "google slides": "https://slides.google.com",
               "google translate": "https://translate.google.com", "netflix": "https://www.netflix.com",
               "linkedin": "https://www.linkedin.com", "twitter": "https://x.com", "reddit": "https://www.reddit.com",
               "pinterest": "https://www.pinterest.com", "canva": "https://www.canva.com",
               "wikipedia": "https://id.wikipedia.org", "tokopedia": "https://www.tokopedia.com",
               "shopee": "https://shopee.co.id", "kbbi": "https://kbbi.kemdikbud.go.id",
               "detik": "https://www.detik.com", "kompas": "https://www.kompas.com",
               "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "gemini": "https://gemini.google.com"}


@cmd(rx=r"\b(?:buka|kunjungi|pergi ke|tampilkan)\b.*\b(" + "|".join(sorted(EXTRA_SITES, key=len, reverse=True)) + r")\b")
def h_more_sites(b, c, m):
    b.say(f"Membuka {m.group(1)}.")
    webbrowser.open(EXTRA_SITES[m.group(1)])


@cmd(rx=r"\b(?:buka|kunjungi)\b.*?\b((?:[a-z0-9-]+\.)+(?:com|co\.id|id|net|org|io|ac\.id|go\.id|dev))\b")
def h_domain(b, c, m):
    b.say(f"Membuka {m.group(1)}.")
    webbrowser.open("https://" + m.group(1))


def _open(b, say, url):
    b.say(say)
    webbrowser.open(url)


@cmd(rx=r"cari gambar (.+)")
def h_images(b, c, m):
    _open(b, f"Mencari gambar {m.group(1)}.", "https://www.google.com/search?tbm=isch&q=" + q(m.group(1)))


@cmd(rx=r"cari (?:di )?tokopedia (.+)")
def h_toped(b, c, m):
    _open(b, f"Mencari {m.group(1)} di Tokopedia.", "https://www.tokopedia.com/search?q=" + q(m.group(1)))


@cmd(rx=r"cari (?:di )?shopee (.+)")
def h_shopee(b, c, m):
    _open(b, f"Mencari {m.group(1)} di Shopee.", "https://shopee.co.id/search?keyword=" + q(m.group(1)))


@cmd(rx=r"(?:cari|cek) harga (.+)")
def h_price(b, c, m):
    _open(b, f"Mencari harga {m.group(1)}.", "https://www.google.com/search?tbm=shop&q=" + q(m.group(1)))


@cmd(rx=r"\b(?:rute|navigasi|petunjuk arah|arahkan(?: saya)?) ke (.+)")
def h_route(b, c, m):
    _open(b, f"Membuka rute ke {m.group(1)}.",
          "https://www.google.com/maps/dir/?api=1&destination=" + q(m.group(1)))


@cmd(rx=r"(?:cari lokasi|cari di maps|di mana letak) (.+)|^(.+?) (?:terdekat|dekat sini)$")
def h_maps(b, c, m):
    place = m.group(1) or (m.group(2) + " terdekat")
    _open(b, f"Mencari {place} di peta.", "https://www.google.com/maps/search/" + q(place))


@cmd(rx=r"kirim pesan whatsapp ke (\+?[\d ]{8,16})\s*(?:isi|pesan|bilang)?\s*(.*)")
def h_wa(b, c, m):
    number = re.sub(r"\D", "", m.group(1))
    if number.startswith("0"):
        number = "62" + number[1:]
    _open(b, "Membuka WhatsApp. Periksa pesannya lalu tekan kirim.",
          f"https://wa.me/{number}?text={q(m.group(2))}")


@cmd(rx=r"(?:kirim|tulis) email(?: ke (\S+(?: at \S+)?(?: titik \S+)*))?")
def h_email(b, c, m):
    to = (m.group(1) or "").replace(" at ", "@").replace(" titik ", ".")
    _open(b, "Membuka draf email.", "mailto:" + to)


# =========================================================
# HIBURAN, ACAK, GAME
# =========================================================

MOTIVASI = ["Mulai saja dulu. Langkah kecil hari ini lebih baik daripada rencana sempurna besok.",
            "Konsisten mengalahkan bakat ketika bakat tidak konsisten.",
            "Kesalahan bukan akhir, hanya cara belajar yang mahal dan berharga.",
            "Kamu tidak harus hebat untuk memulai, tetapi kamu harus memulai untuk menjadi hebat.",
            "Istirahat itu bagian dari proses, bukan kemalasan.",
            "Satu bug yang selesai hari ini adalah satu masalah yang tidak akan kamu temui besok."]
FAKTA = ["Madu hampir tidak pernah basi. Madu berusia ribuan tahun di makam Mesir masih bisa dimakan.",
         "Gurita punya tiga jantung dan darahnya berwarna biru.",
         "Indonesia memiliki lebih dari tujuh belas ribu pulau.",
         "Cahaya matahari butuh sekitar delapan menit untuk sampai ke Bumi.",
         "Pisang secara botani termasuk buah beri, sedangkan stroberi bukan.",
         "Komputer pertama yang menyimpan program di memorinya lahir pada akhir tahun empat puluhan."]
PANTUN = ["Buah duku buah kedondong. Kalau rajin pasti untung, kalau malas cuma bengong.",
          "Pergi ke pasar membeli ketan. Jangan lupa membawa kunci, rajin belajar biar pintar teman.",
          "Jalan-jalan ke kota Medan. Jangan lupa membeli bika, kalau kerja penuh ketekunan, hasilnya pasti bahagia.",
          "Ikan hiu makan tomat. Kalau kamu mau selamat, jangan lupa simpan berkas dahulu sebelum terlambat."]
RIDDLES = [("Apa yang makin dipotong makin panjang?", "Jalan tol atau parit."),
           ("Binatang apa yang paling tinggi lompatannya?", "Kucing, karena selalu melompat ke atas genteng. Bercanda, jawabannya kanguru."),
           ("Apa yang punya kunci tapi tidak bisa membuka pintu?", "Keyboard."),
           ("Semakin diisi, semakin ringan. Apakah itu?", "Balon.")]
JOKES = ["Kenapa komputer tidak pernah lapar? Karena dia sudah punya banyak byte.",
         "Apa persamaan deadline dan mantan? Sama-sama datang tanpa diundang.",
         "Kenapa programmer suka gelap? Karena cahaya mengundang bug.",
         "Kenapa laptop selalu dingin? Karena banyak jendela yang terbuka."]


@cmd("lelucon", "bercanda", "hibur aku", "beri aku lelucon")
def h_joke(b, c, m):
    b.say(random.choice(JOKES))


@cmd("kutipan motivasi", "motivasi", "beri semangat")
def h_motivation(b, c, m):
    b.say(random.choice(MOTIVASI))


@cmd("fakta menarik", "fakta unik", "beri fakta")
def h_fact(b, c, m):
    b.say(random.choice(FAKTA))


@cmd("pantun")
def h_pantun(b, c, m):
    b.say(random.choice(PANTUN))


@cmd("teka-teki", "teka teki")
def h_riddle(b, c, m):
    r = random.choice(RIDDLES)
    b.riddle = r
    b.say(r[0] + " Katakan jawabannya kalau menyerah.")


@cmd("jawabannya", "apa jawabannya", "jawaban teka")
def h_answer(b, c, m):
    r = getattr(b, "riddle", None)
    b.say(r[1] if r else "Belum ada teka-teki. Katakan teka-teki dulu.")


@cmd("lempar koin", "koin")
def h_coin(b, c, m):
    b.say(random.choice(["Gambar.", "Angka."]))


@cmd("lempar dadu", "gulung dadu")
def h_dice(b, c, m):
    b.say(f"Dadunya menunjukkan {random.randint(1, 6)}.")


@cmd(rx=r"angka acak(?: antara)?\s*(\d+)\s*(?:sampai|sampe|hingga|dan|-)\s*(\d+)")
def h_random(b, c, m):
    lo, hi = sorted((int(m.group(1)), int(m.group(2))))
    b.say(f"Angkanya {random.randint(lo, hi)}.")


@cmd(rx=r"^(?:pilih|pilihkan)(?: antara)? (.+?) atau (.+)$")
def h_choose(b, c, m):
    b.say(f"Saya pilih {random.choice([m.group(1), m.group(2)])}.")


@cmd(rx=r"(?:buat|buatkan) kata sandi(?: (\d+))?")
def h_password(b, c, m):
    n = max(8, min(40, int(m.group(1) or 14)))
    pwd = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%&*?") for _ in range(n))
    set_clipboard(pwd)
    b.app.log("sys", f"Kata sandi: {pwd}")
    b.say(f"Kata sandi {n} karakter dibuat dan disalin ke clipboard. Nova tidak membacakannya demi keamanan.")


@cmd("main tebak angka", "tebak angka")
def h_guess(b, c, m):
    b.game = {"type": "guess", "n": random.randint(1, 100), "tries": 0}
    b.say("Saya memikirkan angka dari 1 sampai 100. Sebutkan tebakanmu. Katakan menyerah untuk berhenti.")


@cmd("main suit", "gunting batu kertas")
def h_rps(b, c, m):
    b.game = {"type": "rps", "score": [0, 0]}
    b.say("Ayo suit. Katakan gunting, batu, atau kertas. Katakan berhenti main untuk selesai.")


def play_game(b, c):
    g = b.game
    if re.search(r"\b(menyerah|berhenti main|udahan|selesai main)\b", c):
        b.game = None
        b.say(f"Baik. Angkanya {g['n']}." if g["type"] == "guess" else
              f"Skor akhir: kamu {g['score'][0]}, Nova {g['score'][1]}.")
        return True
    if g["type"] == "guess":
        mm = re.search(r"\d+", c)
        if not mm:
            return False
        n = int(mm.group())
        g["tries"] += 1
        if n == g["n"]:
            b.game = None
            b.say(f"Benar! Angkanya {n}. Kamu menebak dalam {g['tries']} kali.")
        else:
            b.say("Terlalu kecil." if n < g["n"] else "Terlalu besar.")
        return True
    mm = re.search(r"\b(gunting|batu|kertas)\b", c)
    if not mm:
        return False
    you, me = mm.group(1), random.choice(["gunting", "batu", "kertas"])
    beats = {"gunting": "kertas", "batu": "gunting", "kertas": "batu"}
    if you == me:
        res = "Seri."
    elif beats[you] == me:
        g["score"][0] += 1
        res = "Kamu menang."
    else:
        g["score"][1] += 1
        res = "Nova menang."
    b.say(f"Saya pilih {me}. {res} Skor kamu {g['score'][0]}, Nova {g['score'][1]}.")
    return True
