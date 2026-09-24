"""
Nova - asisten suara dengan antarmuka grafis (Windows).

Wajib : pip install sounddevice scipy numpy SpeechRecognition pyttsx3 pyautogui pillow
Opsional: pip install edge-tts pygame   -> suara natural yang jauh lebih halus (butuh internet)
          pip install psutil            -> info baterai, CPU, RAM, aplikasi berjalan
          pip install tzdata opencv-python -> jam dunia, ambil foto
Fitur tambahan ada di nova_features.py (satu folder dengan file ini).
"""
import os
import re
import math
import time
import queue
import random
import ctypes
import asyncio
import tempfile
import threading
import subprocess
import webbrowser
import datetime
import urllib.parse
import tkinter as tk
from tkinter import ttk
from collections import deque

import numpy as np
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
import pyautogui

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import edge_tts
    import pygame
    pygame.mixer.init()
    HAS_NEURAL = True
except Exception:
    HAS_NEURAL = False

try:
    import psutil
except Exception:
    psutil = None

try:
    import nova_features as features   # paket fitur tambahan (file nova_features.py)
except Exception as _error:
    features = None
    print("Fitur tambahan tidak dimuat:", _error)


# =========================================================
# KONFIGURASI
# =========================================================

SAMPLE_RATE = 16000
MAX_RECORD_SECONDS = 10      # batas panjang satu perintah
WAIT_SPEECH_SECONDS = 6      # menunggu kamu mulai bicara
END_SILENCE_SECONDS = 1.0    # jeda hening yang dianggap perintah selesai
MIN_THRESHOLD = 350          # naikkan bila ruangan berisik

SCREENSHOT_FOLDER = "screenshots"
NOTES_FILE = "nova_catatan.txt"

BG = "#0C1120"
PANEL = "#141B30"
PANEL2 = "#1E2846"
TEXT = "#E8ECF8"
MUTED = "#8A94B2"
AQUA = "#5EEAD4"
AMBER = "#FBBF24"
VIOLET = "#A78BFA"
SKY = "#7DD3FC"
OFF = "#3B4463"

STATE_COLOR = {"off": OFF, "listening": AQUA, "thinking": AMBER, "speaking": VIOLET}
STATE_TEXT = {
    "off": "Nova nonaktif",
    "listening": "Mendengarkan...",
    "thinking": "Memproses...",
    "speaking": "Berbicara...",
}

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "maps": "https://maps.google.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "tiktok": "https://www.tiktok.com",
    "whatsapp": "https://web.whatsapp.com",
}

APPS = [
    (("kalkulator", "calculator"), "kalkulator", ["calc.exe"]),
    (("notepad",), "Notepad", ["notepad.exe"]),
    (("paint",), "Paint", ["mspaint.exe"]),
    (("file explorer", "explorer"), "File Explorer", ["explorer.exe"]),
    (("task manager", "pengelola tugas"), "Task Manager", ["taskmgr.exe"]),
    (("pengaturan", "settings"), "Pengaturan", ["cmd", "/c", "start", "", "ms-settings:"]),
    (("terminal", "command prompt"), "Command Prompt", ["cmd", "/c", "start", "cmd"]),
    (("chrome",), "Google Chrome", ["cmd", "/c", "start", "", "chrome"]),
    (("edge",), "Microsoft Edge", ["cmd", "/c", "start", "", "msedge"]),
]

JOKES = [
    "Kenapa komputer tidak pernah lapar? Karena dia sudah punya banyak byte.",
    "Apa persamaan deadline dan mantan? Sama-sama datang tanpa diundang.",
    "Kenapa programmer suka gelap? Karena cahaya mengundang bug.",
    "Kenapa laptop selalu dingin? Karena banyak jendela yang terbuka.",
]


def mix(a, b, t):
    """Campur dua warna hex; t=0 -> a, t=1 -> b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ca, cb))


# =========================================================
# TEXT TO SPEECH (satu thread khusus, antrean, bisa dihentikan)
# =========================================================

class Speaker:
    def __init__(self):
        self.q = queue.Queue()
        self.rate = 170
        self.volume = 1.0
        self.voices = {}
        self.default_label = None
        self.current = None
        self.sapi_fallback = None
        self.pending = 0
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.ready = threading.Event()
        self.last_end = 0.0
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def busy(self):
        return self.pending > 0

    def _loop(self):
        engine = pyttsx3.init()

        def on_word(name, location, length):
            if self.stop_flag.is_set():
                engine.stop()

        engine.connect("started-word", on_word)

        sapi, indo = {}, None
        for v in engine.getProperty("voices"):
            label = f"{v.name} (suara sistem)"
            sapi[label] = ("sapi", v.id)
            if indo is None and re.search(r"indones|andika|id-id", v.name + v.id, re.I):
                indo = label

        if HAS_NEURAL:
            self.voices["Gadis - natural (butuh internet)"] = ("neural", "id-ID-GadisNeural")
            self.voices["Ardi - natural (butuh internet)"] = ("neural", "id-ID-ArdiNeural")
        self.voices.update(sapi)
        self.sapi_fallback = sapi.get(indo) or next(iter(sapi.values()), None)

        if HAS_NEURAL:
            self.default_label = next(iter(self.voices))
        else:
            self.default_label = indo or next(iter(sapi), None)
        self.current = self.voices.get(self.default_label)
        self.ready.set()

        while True:
            text, done = self.q.get()
            self.stop_flag.clear()
            try:
                if not (self.current and self.current[0] == "neural" and self._neural(text)):
                    self._sapi(engine, text)
            except Exception as error:
                print("TTS error:", error)
            finally:
                with self.lock:
                    self.pending -= 1
                self.last_end = time.time()
                done.set()

    def _sapi(self, engine, text):
        voice = self.current if self.current and self.current[0] == "sapi" else self.sapi_fallback
        if voice:
            engine.setProperty("voice", voice[1])
        engine.setProperty("rate", int(self.rate))
        engine.setProperty("volume", self.volume)
        engine.say(text)
        engine.runAndWait()

    def _neural(self, text):
        try:
            path = os.path.join(tempfile.gettempdir(), "nova_tts.mp3")
            pct = int((self.rate - 170) / 170 * 100)

            async def generate():
                await edge_tts.Communicate(text, self.current[1], rate=f"{pct:+d}%").save(path)

            asyncio.run(generate())
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.stop_flag.is_set():
                time.sleep(0.05)
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            return True
        except Exception as error:
            print("Suara natural gagal, memakai suara sistem:", error)
            return False

    def select(self, label):
        self.current = self.voices[label]

    def say(self, text, wait=True):
        done = threading.Event()
        with self.lock:
            self.pending += 1
        self.q.put((text, done))
        if wait:
            done.wait()

    def stop(self):
        self.stop_flag.set()
        try:
            while True:
                _, done = self.q.get_nowait()
                with self.lock:
                    self.pending -= 1
                done.set()
        except queue.Empty:
            pass


# =========================================================
# OTAK NOVA: memproses perintah
# =========================================================

class Brain:
    def __init__(self, app):
        self.app = app
        self.awaiting = None     # menunggu jawaban ya/tidak
        self.mode = None         # mode khusus, misalnya dikte
        self.game = None         # game yang sedang dimainkan
        self.last_files = []     # hasil pencarian file terakhir

    def say(self, text):
        self.app.say(text)

    def handle(self, command):
        cmd = command.lower().strip()
        if not cmd:
            return
        self.app.log("user", cmd)
        has = lambda *words: any(w in cmd for w in words)

        if features and features.dispatch(self, cmd):
            return
        if has("keluar", "berhenti", "matikan nova", "tutup assistant", "tutup asisten"):
            self.say("Baik. Nova dimatikan. Sampai jumpa.")
            self.app.ui.put(("off",))
            return
        if re.search(r"\b(halo|hai|hello|hi)\b", cmd):
            self.say("Halo. Saya Nova. Apa yang bisa saya bantu?")
            return
        if has("bantuan", "bisa apa", "fitur apa"):
            self.say("Saya bisa membuka aplikasi dan website, mencari di Google dan YouTube, "
                     "mengambil screenshot, mengatur volume, membuat timer dan catatan, "
                     "berhitung, serta memberi tahu waktu dan tanggal.")
            return
        if has("jam berapa", "sekarang jam", "pukul berapa"):
            self.say("Sekarang pukul " + datetime.datetime.now().strftime("%H.%M") + ".")
            return
        if has("tanggal berapa", "tanggal hari ini", "hari apa"):
            n = datetime.datetime.now()
            self.say(f"Hari ini {HARI[n.weekday()]}, {n.day} {BULAN[n.month - 1]} {n.year}.")
            return
        if has("screenshot", "screen shot", "tangkap layar", "ambil layar"):
            self.screenshot()
            return
        if has("volume", "bisukan", "mute"):
            self.volume(cmd)
            return
        if has("timer", "ingatkan", "pengingat") and re.search(r"\d+\s*(detik|menit|jam)", cmd):
            self.timer(cmd)
            return
        if has("baca catatan", "lihat catatan", "isi catatan"):
            self.read_notes()
            return
        if has("catat", "catatan"):
            self.add_note(cmd)
            return
        if "hitung" in cmd or re.search(r"\d+\s*(\+|-|\*|/|x|tambah|kurang|kali|bagi|dibagi)\s*\d+", cmd):
            self.calculate(cmd)
            return
        if has("cari video", "cari di youtube", "putar video", "cari youtube"):
            self.search("youtube", cmd, ["cari video", "cari di youtube", "putar video", "cari youtube"])
            return
        if has("cari di google", "cari di internet") or cmd.startswith("cari "):
            self.search("google", cmd, ["cari di google", "cari di internet", "cari"])
            return
        if has("cuaca"):
            self.say("Membuka prakiraan cuaca.")
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote("cuaca hari ini"))
            return
        if has("baterai"):
            self.battery()
            return
        if has("kunci layar", "kunci komputer"):
            self.say("Mengunci layar.")
            ctypes.windll.user32.LockWorkStation()
            return
        if has("lelucon", "bercanda", "hibur aku"):
            self.say(random.choice(JOKES))
            return
        if has("terima kasih", "makasih"):
            self.say("Sama-sama.")
            return
        if has("siapa kamu", "siapa namamu"):
            self.say("Saya Nova, asisten suara di komputermu.")
            return
        if self.open_folder(cmd) or self.open_website(cmd) or self.open_app(cmd):
            return
        self.say("Maaf, saya belum memahami perintah itu. Katakan bantuan untuk melihat yang bisa saya lakukan.")

    # ---------- fitur ----------

    def screenshot(self):
        os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(SCREENSHOT_FOLDER, f"screenshot_{stamp}.png")
        try:
            pyautogui.screenshot().save(path)
            self.app.log("sys", f"Tersimpan: {os.path.abspath(path)}")
            self.say("Screenshot berhasil disimpan.")
        except Exception as error:
            self.app.log("sys", f"Screenshot gagal: {error}")
            self.say("Saya gagal mengambil screenshot.")

    def volume(self, cmd):
        if any(w in cmd for w in ("naik", "tambah", "besar")):
            pyautogui.press("volumeup", presses=5)
            self.say("Volume dinaikkan.")
        elif any(w in cmd for w in ("turun", "kurang", "kecil")):
            pyautogui.press("volumedown", presses=5)
            self.say("Volume diturunkan.")
        elif any(w in cmd for w in ("bisu", "mute", "matikan")):
            pyautogui.press("volumemute")
            self.say("Volume diubah ke senyap.")
        else:
            self.say("Katakan naikkan volume, turunkan volume, atau bisukan volume.")

    def timer(self, cmd):
        m = re.search(r"(\d+)\s*(detik|menit|jam)", cmd)
        amount, unit = int(m.group(1)), m.group(2)
        seconds = amount * {"detik": 1, "menit": 60, "jam": 3600}[unit]
        label = f"{amount} {unit}"
        t = threading.Timer(seconds, lambda: self.say(f"Timer {label} sudah selesai."))
        t.daemon = True
        t.start()
        self.say(f"Timer {label} dimulai.")

    def add_note(self, cmd):
        text = re.sub(r"^\s*(tolong\s+)?(buat catatan|tulis catatan|catatan|catat)\s*", "", cmd).strip()
        if not text:
            self.say("Sebutkan isi catatan setelah kata catat. Contohnya: catat beli baterai.")
            return
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {text}\n")
        self.say("Catatan disimpan.")

    def read_notes(self):
        if not os.path.exists(NOTES_FILE):
            self.say("Belum ada catatan.")
            return
        with open(NOTES_FILE, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()][-3:]
        if not lines:
            self.say("Belum ada catatan.")
            return
        self.app.log("sys", "\n".join(lines))
        self.say("Catatan terakhir. " + ". ".join(re.sub(r"^\[.*?\]\s*", "", l) for l in lines))

    def calculate(self, cmd):
        expr = cmd.split("hitung", 1)[-1]
        for word, sym in [("ditambah", "+"), ("tambah", "+"), ("dikurangi", "-"), ("kurang", "-"),
                          ("dikali", "*"), ("kali", "*"), (" x ", "*"), ("dibagi", "/"),
                          ("bagi", "/"), (",", ".")]:
            expr = expr.replace(word, sym)
        expr = re.sub(r"[^0-9+\-*/().\s]", "", expr).strip()
        if not expr or "**" in expr:
            self.say("Saya tidak menangkap soal hitungannya.")
            return
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            elif isinstance(result, float):
                result = round(result, 4)
            self.say(f"Hasilnya {str(result).replace('.', ',')}.")
        except ZeroDivisionError:
            self.say("Tidak bisa membagi dengan nol.")
        except Exception:
            self.say("Saya tidak bisa menghitung itu.")

    def search(self, site, cmd, keywords):
        query = cmd
        for k in keywords:
            query = query.replace(k, "")
        query = query.strip()
        if not query:
            self.say("Apa yang ingin kamu cari?")
            return
        q = urllib.parse.quote(query)
        if site == "youtube":
            url = "https://www.youtube.com/results?search_query=" + q
            self.say(f"Mencari video {query}.")
        else:
            url = "https://www.google.com/search?q=" + q
            self.say(f"Mencari {query} di Google.")
        webbrowser.open(url)

    def battery(self):
        info = psutil.sensors_battery() if psutil else None
        if not info:
            self.say("Info baterai tidak tersedia.")
            return
        status = "sedang diisi" if info.power_plugged else "tidak diisi"
        self.say(f"Baterai {int(info.percent)} persen dan {status}.")

    def open_folder(self, cmd):
        home = os.path.expanduser("~")
        for words, folder, label in [(("download", "unduhan"), "Downloads", "Downloads"),
                                     (("document", "dokumen"), "Documents", "Documents"),
                                     (("desktop",), "Desktop", "Desktop")]:
            if any(w in cmd for w in words):
                path = os.path.join(home, folder)
                if os.path.exists(path):
                    self.say(f"Membuka folder {label}.")
                    os.startfile(path)
                    return True
        return False

    def open_website(self, cmd):
        for name, url in WEBSITES.items():
            if name in cmd:
                self.say(f"Membuka {name}.")
                webbrowser.open(url)
                return True
        return False

    def open_app(self, cmd):
        for words, label, args in APPS:
            if any(w in cmd for w in words):
                try:
                    subprocess.Popen(args)
                    self.say(f"Membuka {label}.")
                except Exception:
                    self.say(f"Saya tidak bisa membuka {label}.")
                return True
        return False


# =========================================================
# APLIKASI GUI
# =========================================================

class NovaApp:
    def __init__(self, root):
        self.root = root
        self.ui = queue.Queue()
        self.speaker = Speaker()
        self.brain = Brain(self)
        self.recognizer = sr.Recognizer()
        self.active = threading.Event()
        self.gen = 0
        self.state = "off"
        self.level = 0.0
        self.smooth = 0.0
        self.t = 0.0
        self.last_said = ""

        root.title("Nova")
        root.geometry("980x660")
        root.minsize(860, 580)
        root.configure(bg=BG)
        self.speaker.ready.wait(5)
        self._build()
        self.log("sys", "Tekan tombol di kiri untuk menyalakan Nova, lalu bicara atau ketik perintah. "
                        "Coba: \"buka YouTube\", \"cari video Python\", \"timer 5 menit\", \"hitung 12 kali 8\".")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick()

    # ---------- membangun tampilan ----------

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                        arrowcolor=TEXT, bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL,
                        bordercolor=PANEL, arrowcolor=MUTED)
        self.root.option_add("*TCombobox*Listbox.background", PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)

        left = tk.Frame(self.root, bg=BG, width=320)
        left.pack(side="left", fill="y", padx=(24, 12), pady=20)
        left.pack_propagate(False)
        right = tk.Frame(self.root, bg=PANEL)
        right.pack(side="right", fill="both", expand=True, padx=(12, 24), pady=20)

        tk.Label(left, text="Nova", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 30)).pack(anchor="w")
        tk.Label(left, text="Asisten suara pribadimu", bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(anchor="w")

        self.orb = tk.Canvas(left, width=280, height=260, bg=BG, highlightthickness=0)
        self.orb.pack(pady=(12, 0))
        self.status = tk.Label(left, text=STATE_TEXT["off"], bg=BG, fg=MUTED, font=("Segoe UI", 12))
        self.status.pack(pady=(0, 10))

        self.switch = tk.Canvas(left, width=112, height=44, bg=BG, highlightthickness=0, cursor="hand2")
        self.switch.pack()
        self.switch.bind("<Button-1>", lambda e: self.set_active(not self.active.is_set()))
        self.draw_switch()

        box = tk.Frame(left, bg=PANEL, padx=14, pady=12)
        box.pack(fill="x", pady=(18, 0))
        tk.Label(box, text="Suara", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        self.voice_box = ttk.Combobox(box, state="readonly", values=list(self.speaker.voices))
        if self.speaker.default_label:
            self.voice_box.set(self.speaker.default_label)
        self.voice_box.pack(fill="x", pady=(2, 8))
        self.voice_box.bind("<<ComboboxSelected>>", lambda e: self.speaker.select(self.voice_box.get()))

        for label, lo, hi, init, cb in [
            ("Kecepatan bicara", 120, 220, 170, lambda v: setattr(self.speaker, "rate", float(v))),
            ("Volume suara", 30, 100, 100, lambda v: setattr(self.speaker, "volume", float(v) / 100)),
        ]:
            tk.Label(box, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
            s = tk.Scale(box, from_=lo, to=hi, orient="horizontal", showvalue=False, command=cb,
                         bg=PANEL, troughcolor=PANEL2, activebackground=AQUA, highlightthickness=0,
                         bd=0, sliderrelief="flat")
            s.set(init)
            s.pack(fill="x", pady=(0, 6))
        self._button(box, "Uji suara", lambda: threading.Thread(
            target=lambda: self.speaker.say("Halo, ini suara Nova."), daemon=True).start()).pack(fill="x")

        head = tk.Frame(right, bg=PANEL)
        head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text="Percakapan", bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(side="left")
        self._button(head, "Bersihkan", self.clear_chat).pack(side="right")

        body = tk.Frame(right, bg=PANEL)
        body.pack(fill="both", expand=True, padx=18)
        self.chat = tk.Text(body, bg=PANEL, fg=TEXT, relief="flat", wrap="word", state="disabled",
                            font=("Segoe UI", 11), padx=4, pady=6, highlightthickness=0, spacing3=2)
        bar = ttk.Scrollbar(body, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("user_name", foreground=SKY, font=("Segoe UI Semibold", 10))
        self.chat.tag_configure("nova_name", foreground=AQUA, font=("Segoe UI Semibold", 10))
        self.chat.tag_configure("user", foreground=TEXT)
        self.chat.tag_configure("nova", foreground=TEXT)
        self.chat.tag_configure("sys", foreground=MUTED, font=("Segoe UI", 10, "italic"))

        chips = tk.Frame(right, bg=PANEL)
        chips.pack(fill="x", padx=18, pady=(8, 0))
        quick = [("Screenshot", "ambil screenshot"), ("Jam", "jam berapa sekarang"),
                 ("Tanggal", "tanggal hari ini"), ("Cuaca", "cuaca hari ini"),
                 ("Baca catatan", "baca catatan"), ("Volume +", "naikkan volume"),
                 ("Volume -", "turunkan volume"), ("Lelucon", "beri aku lelucon")]
        for i, (label, cmd) in enumerate(quick):
            self._button(chips, label, lambda c=cmd: self.run_text(c)).grid(
                row=i // 4, column=i % 4, padx=3, pady=3, sticky="ew")
            chips.columnconfigure(i % 4, weight=1)

        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x", padx=18, pady=16)
        self.entry = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat",
                              font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send())
        self._button(row, "Kirim", self.send, accent=True).pack(side="right", ipady=4)

    def _button(self, parent, text, command, accent=False):
        bg = AQUA if accent else PANEL2
        fg = BG if accent else TEXT
        hover = mix(bg, "#FFFFFF", 0.12)
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                      activeforeground=fg, relief="flat", bd=0, padx=12, pady=5,
                      font=("Segoe UI", 10), cursor="hand2")
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        return b

    def draw_switch(self):
        c = self.switch
        c.delete("all")
        on = self.active.is_set()
        track = AQUA if on else OFF
        c.create_oval(0, 0, 44, 44, fill=track, outline="")
        c.create_oval(68, 0, 112, 44, fill=track, outline="")
        c.create_rectangle(22, 0, 90, 44, fill=track, outline="")
        knob = 72 if on else 4
        c.create_oval(knob, 4, knob + 36, 40, fill="#FFFFFF", outline="")
        c.create_text(36 if on else 76, 22, text="ON" if on else "OFF",
                      fill=BG if on else TEXT, font=("Segoe UI Semibold", 11))

    def draw_orb(self, state):
        c = self.orb
        c.delete("all")
        cx, cy = 140, 130
        color = STATE_COLOR[state]
        if state == "listening":
            amp = 0.10 + 0.08 * math.sin(self.t * 2.2) + self.smooth * 0.9
        elif state == "speaking":
            amp = 0.40 + 0.22 * math.sin(self.t * 9) + 0.12 * math.sin(self.t * 5.3)
        elif state == "thinking":
            amp = 0.15
        else:
            amp = 0.0
        amp = max(0.0, min(1.2, amp))
        base = 50
        for i in range(5, 0, -1):
            r = base + i * 8 + amp * i * 5
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(BG, color, 0.05 * (6 - i)), outline="")
        r = base + amp * 8
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(color, "#FFFFFF", 0.08), outline="")
        h = r * 0.36
        hx, hy = cx - r * 0.28, cy - r * 0.32
        c.create_oval(hx - h, hy - h, hx + h, hy + h, fill=mix(color, "#FFFFFF", 0.45), outline="")
        if state == "thinking":
            rr = r + 14
            c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=-self.t * 240 % 360,
                         extent=100, style="arc", outline=color, width=4)

    # ---------- log & antrean UI ----------

    def log(self, kind, text):
        self.ui.put(("log", kind, text))

    def _append(self, kind, text):
        t = self.chat
        t.configure(state="normal")
        if kind == "sys":
            t.insert("end", f"{text}\n\n", "sys")
        else:
            stamp = datetime.datetime.now().strftime("%H:%M")
            t.insert("end", ("Kamu" if kind == "user" else "Nova") + f"  {stamp}\n", kind + "_name")
            t.insert("end", f"{text}\n\n", kind)
        t.configure(state="disabled")
        t.see("end")

    def clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")

    def tick(self):
        try:
            while True:
                item = self.ui.get_nowait()
                if item[0] == "log":
                    self._append(item[1], item[2])
                elif item[0] == "off":
                    self.set_active(False)
                elif item[0] == "clear":
                    self.clear_chat()
                elif item[0] == "voice":
                    self.voice_box.set(item[1])
        except queue.Empty:
            pass

        if not self.active.is_set():
            state = "off"
        elif self.speaker.busy:
            state = "speaking"
        else:
            state = self.state
        self.t += 0.033
        self.smooth += (self.level - self.smooth) * 0.25
        self.draw_orb(state)
        self.status.configure(text=STATE_TEXT[state], fg=STATE_COLOR[state] if state != "off" else MUTED)
        self.root.after(33, self.tick)

    # ---------- kontrol ON / OFF ----------

    def set_active(self, on):
        if on == self.active.is_set():
            return
        if on:
            self.active.set()
            self.gen += 1
            hour = datetime.datetime.now().hour
            part = "pagi" if hour < 11 else "siang" if hour < 15 else "sore" if hour < 18 else "malam"
            greeting = f"Selamat {part}. Nova siap digunakan."
            self.log("nova", greeting)
            self.speaker.say(greeting, wait=False)
            threading.Thread(target=self.listen_loop, args=(self.gen,), daemon=True).start()
        else:
            self.active.clear()
            self.gen += 1
            self.speaker.stop()
            self.level = 0.0
            self.log("sys", "Nova dimatikan.")
        self.draw_switch()

    def say(self, text):
        self.last_said = text
        self.log("nova", text)
        self.speaker.say(text, wait=True)

    def send(self):
        text = self.entry.get()
        self.entry.delete(0, "end")
        self.run_text(text)

    def run_text(self, text):
        text = text.strip()
        if not text:
            return
        if not self.active.is_set():
            self.log("sys", "Nyalakan Nova dulu dengan tombol di sebelah kiri.")
            return
        threading.Thread(target=self.brain.handle, args=(text,), daemon=True).start()

    # ---------- mendengarkan ----------

    @staticmethod
    def _rms(data):
        return float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))

    def record_until_silence(self, gen):
        block = int(SAMPLE_RATE * 0.1)
        preroll = deque(maxlen=3)
        frames, started, silence, waited = [], False, 0, 0
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block) as stream:
            ambient = [self._rms(stream.read(block)[0]) for _ in range(4)]
            threshold = max(MIN_THRESHOLD, float(np.mean(ambient)) * 2.5)
            for _ in range(int(MAX_RECORD_SECONDS * 10)):
                if not self.active.is_set() or gen != self.gen:
                    return None
                data, _overflow = stream.read(block)
                level = self._rms(data)
                self.level = min(1.0, level / 3000)
                if level > threshold:
                    if not started:
                        frames = list(preroll)
                        started = True
                    silence = 0
                elif started:
                    silence += 1
                if started:
                    frames.append(data)
                    if silence >= int(END_SILENCE_SECONDS * 10):
                        break
                else:
                    preroll.append(data)
                    waited += 1
                    if waited >= WAIT_SPEECH_SECONDS * 10:
                        return None
        self.level = 0.0
        return np.concatenate(frames) if frames else None

    def recognize(self, audio):
        try:
            data = sr.AudioData(audio.tobytes(), SAMPLE_RATE, 2)
            return self.recognizer.recognize_google(data, language="id-ID").lower()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            self.log("sys", "Pengenalan suara butuh koneksi internet.")
            time.sleep(2)
            return ""

    def listen_loop(self, gen):
        while self.active.is_set() and gen == self.gen:
            if self.speaker.busy or time.time() - self.speaker.last_end < 0.6:
                self.level = 0.0
                time.sleep(0.1)
                continue
            self.state = "listening"
            try:
                audio = self.record_until_silence(gen)
            except Exception as error:
                self.log("sys", f"Mikrofon bermasalah: {error}")
                self.ui.put(("off",))
                return
            if audio is None or gen != self.gen:
                continue
            self.state = "thinking"
            text = self.recognize(audio)
            if text and gen == self.gen:
                self.brain.handle(text)
        self.state = "listening"

    def on_close(self):
        self.active.clear()
        self.gen += 1
        self.speaker.stop()
        self.root.destroy()


# =========================================================
# START PROGRAM
# =========================================================

if __name__ == "__main__":
    window = tk.Tk()
    NovaApp(window)
    window.mainloop()
