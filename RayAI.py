"""
Ray Assistant - Voice Assistant (Complete Edition with Male Voice Default)

Persyaratan Pustaka:
    pip install sounddevice scipy numpy SpeechRecognition pyttsx3 pyautogui pillow pywhatkit edge-tts pygame psutil opencv-python
"""

import os
import re
import sys
import math
import time
import json
import queue
import random
import ctypes
import socket
import asyncio
import tempfile
import threading
import subprocess
import webbrowser
import datetime
import urllib.parse
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk
from collections import deque

import numpy as np
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
import pyautogui

# Pustaka Opsional / Pendukung
try:
    import pywhatkit
    HAS_WHATKIT = True
except Exception:
    HAS_WHATKIT = False

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
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

# =========================================================
# KONFIGURASI GLOBAL & UTILITY
# =========================================================

SAMPLE_RATE = 16000
MAX_RECORD_SECONDS = 10
WAIT_SPEECH_SECONDS = 6
END_SILENCE_SECONDS = 1.0
MIN_THRESHOLD = 350

SCREENSHOT_FOLDER = "screenshots"
RECORDING_FOLDER = "screen_recordings"
NOTES_FILE = "ray_assistant_catatan.txt"
PHOTO_FOLDER = "photos"

NOWIN = 0x08000000 if os.name == "nt" else 0

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
    "off": "Ray Assistant nonaktif",
    "listening": "Mendengarkan...",
    "thinking": "Memproses...",
    "speaking": "Berbicara...",
}

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]

# Mapping Website Populer
WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google scholar": "https://scholar.google.com",
    "scholar": "https://scholar.google.com",
    "jurnal": "https://scholar.google.com",
    "maps": "https://maps.google.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "tiktok": "https://www.tiktok.com",
    "whatsapp": "https://web.whatsapp.com",
    "chatgpt": "https://chatgpt.com",
    "wikipedia": "https://id.wikipedia.org",
}

# Mapping Aplikasi untuk Membuka
APP_OPEN_MAP = {
    "kamera": "microsoft.windows.camera:",
    "camera": "microsoft.windows.camera:",
    "foto": "ms-photos:",
    "galeri": "ms-photos:",
    "kalkulator": "calc",
    "calculator": "calc",
    "catatan": "notepad",
    "notepad": "notepad",
    "pengaturan": "ms-settings:",
    "setting": "ms-settings:",
    "settings": "ms-settings:",
    "store": "ms-windows-store:",
    "cmd": "cmd",
    "command prompt": "cmd",
    "terminal": "wt",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "chrome": "chrome",
    "edge": "msedge",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "code": "code",
    "spotify": "spotify",
    "whatsapp": "whatsapp:",
}

# Mapping Aplikasi untuk Menutup
APP_PROCESS_MAP = {
    "visual studio code": ["code.exe"],
    "vs code": ["code.exe"],
    "vscode": ["code.exe"],
    "vsc": ["code.exe"],
    "code": ["code.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "opera": ["opera.exe"],
    "notepad": ["notepad.exe"],
    "catatan": ["notepad.exe"],
    "kalkulator": ["calculatorapp.exe", "calc.exe", "calculator.exe"],
    "calculator": ["calculatorapp.exe", "calc.exe"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "spotify": ["spotify.exe"],
    "whatsapp": ["whatsapp.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "terminal": ["windowsterminal.exe"],
    "foto": ["photos.exe", "microsoft.photos.exe"],
    "galeri": ["photos.exe", "microsoft.photos.exe"],
    "kamera": ["windowscamera.exe", "camera.exe"],
    "camera": ["windowscamera.exe", "camera.exe"],
    "pengaturan": ["systemsettings.exe"],
    "setting": ["systemsettings.exe"]
}

JOKES = [
    "Kenapa komputer tidak pernah lapar? Karena dia sudah punya banyak byte.",
    "Apa persamaan deadline dan mantan? Sama-sama datang tanpa diundang.",
    "Kenapa programmer suka gelap? Karena cahaya mengundang bug.",
    "Kenapa laptop selalu dingin? Karena banyak jendela yang terbuka.",
]

def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ca, cb))

def http_get(url, timeout=8):
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# =========================================================
# PEMINDAI APLIKASI SISTEM (APP SCANNER)
# =========================================================

class AppScanner:
    def __init__(self):
        self.apps = {}
        self.refresh()

    def refresh(self):
        self.apps.clear()
        if os.name != "nt":
            return

        start_dirs = [
            os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
        ]
        for s_dir in start_dirs:
            if os.path.exists(s_dir):
                for root_dir, _, files in os.walk(s_dir):
                    for file in files:
                        if file.endswith(".lnk"):
                            name = os.path.splitext(file)[0].lower()
                            self.apps[name] = os.path.join(root_dir, file)

    def launch(self, query):
        query = query.lower().strip()
        if query in self.apps:
            try:
                os.startfile(self.apps[query])
                return True
            except Exception:
                return False

        for name, path in self.apps.items():
            if query in name or name in query:
                try:
                    os.startfile(path)
                    return True
                except Exception:
                    continue
        return False

app_scanner = AppScanner()


# =========================================================
# SCREEN RECORDER
# =========================================================

class ScreenRecorder:
    def __init__(self):
        self.is_recording = False
        self.thread = None
        self.filepath = ""

    def start(self):
        if self.is_recording:
            return False
        self.is_recording = True
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if not self.is_recording:
            return None
        self.is_recording = False
        if self.thread:
            self.thread.join()
        return self.filepath

    def _record_loop(self):
        os.makedirs(RECORDING_FOLDER, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.filepath = os.path.join(RECORDING_FOLDER, f"rekaman_{stamp}.avi")

        first_img = pyautogui.screenshot()
        frame_sample = np.array(first_img)
        height, width, _ = frame_sample.shape

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out = cv2.VideoWriter(self.filepath, fourcc, 10.0, (width, height))

        while self.is_recording:
            img = pyautogui.screenshot()
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            out.write(frame)
            time.sleep(1.0 / 10.0)

        out.release()

screen_recorder = ScreenRecorder()


# =========================================================
# TEXT TO SPEECH (TTS) - DENGAN SUARA DEFAULT COWO (ARDI)
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

        sapi, indo, sapi_male = {}, None, None
        for v in engine.getProperty("voices"):
            label = f"{v.name} (suara sistem)"
            sapi[label] = ("sapi", v.id)
            if indo is None and re.search(r"indones|andika|id-id", v.name + v.id, re.I):
                indo = label
            if sapi_male is None and re.search(r"andika|male|pria|david|stefan", v.name + v.id, re.I):
                sapi_male = label

        if HAS_NEURAL:
            self.voices["Ardi (Cowo) - natural (butuh internet)"] = ("neural", "id-ID-ArdiNeural")
            self.voices["Gadis (Cewek) - natural (butuh internet)"] = ("neural", "id-ID-GadisNeural")
        
        self.voices.update(sapi)
        self.sapi_fallback = sapi.get(sapi_male) or sapi.get(indo) or next(iter(sapi.values()), None)

        if HAS_NEURAL:
            self.default_label = "Ardi (Cowo) - natural (butuh internet)"
        else:
            self.default_label = sapi_male or indo or next(iter(sapi), None)
            
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
            path = os.path.join(tempfile.gettempdir(), "ray_assistant_tts.mp3")
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
# BRAIN (LOGIKA PEMROSES PERINTAH)
# =========================================================

class Brain:
    def __init__(self, app):
        self.app = app
        self.awaiting = None
        self.mode = None

    def say(self, text):
        self.app.say(text)

    def show_help(self):
        help_text = (
            "📌 FITUR & PERINTAH RAY ASSISTANT:\n"
            "• Pencarian Cerdas: 'cari jurnal [topik] dan buka', 'buka artikel tentang [topik]'\n"
            "• Musik: 'putar [judul lagu]'\n"
            "• Buka Aplikasi: 'buka foto', 'buka kamera', 'buka whatsapp', 'buka vs code'\n"
            "• Tutup Aplikasi/Web: 'tutup kamera', 'tutup chrome', 'tutup tab', 'tutup vs code'\n"
            "• Catatan: 'catat [isi]', 'baca catatan'\n"
            "• Timer: 'timer [angka] menit/detik'\n"
            "• Tangkap Layar: 'screenshot', 'mulai rekam layar', 'stop rekam layar'\n"
            "• Sistem: 'info sistem', 'baterai', 'kunci layar', 'volume naik/turun'\n"
            "• Lainnya: 'cari [topik]', 'hitung 15x4', 'jam berapa', 'tanggal berapa'"
        )
        self.app.log("sys", help_text)
        self.say("Berikut adalah daftar fitur yang bisa saya lakukan.")

    def handle(self, command):
        cmd = command.lower().strip()
        if not cmd:
            return
        self.app.log("user", cmd)
        has = lambda *words: any(w in cmd for w in words)

        # 1. Eksekusi Modul Ekstensi / Dikte / Rekam Layar / Tutup Aplikasi
        if dispatch_features(self, cmd):
            return

        # 2. Catatan
        if has("baca catatan", "lihat catatan", "isi catatan"):
            self.read_notes()
            return
        if has("catat", "catatan"):
            self.add_note(cmd)
            return

        # 3. Bantuan & Daftar Fitur
        if has("bantuan", "bisa apa", "fitur", "itu saja", "ada apa saja", "menu"):
            self.show_help()
            return

        # 4. Pencarian Cerdas Langsung Buka
        if self.smart_search_and_open(cmd):
            return

        # 5. Pemutaran Musik / Video YouTube
        if has("putar", "putarkan", "play", "dengarkan") or ("lagu" in cmd and not has("catat", "tulis")):
            self.play_youtube_direct(cmd)
            return

        # 6. Keluar / Matikan Ray Assistant
        if has("keluar", "berhenti", "matikan ray", "matikan asisten", "tutup assistant", "tutup asisten"):
            self.say("Baik, Ray Assistant dimatikan. Sampai jumpa.")
            self.app.ui.put(("off",))
            return

        # 7. Sapaan & Informasi Umum
        if re.search(r"\b(halo|hai|hello|hi)\b", cmd):
            self.say("Halo, ada yang bisa Ray Assistant bantu?")
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
        if "hitung" in cmd or re.search(r"\d+\s*(\+|-|\*|/|x|tambah|kurang|kali|bagi|dibagi)\s*\d+", cmd):
            self.calculate(cmd)
            return
        if has("cari di google", "cari di internet") or cmd.startswith("cari "):
            self.search_google(cmd)
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
            self.say("Sama-sama!")
            return
        if has("siapa kamu", "siapa namamu"):
            self.say("Saya Ray Assistant, asisten suara berbasis AI untuk komputermu.")
            return

        # 8. Buka Folder, Website, atau Aplikasi Komputer
        if self.open_folder(cmd) or self.open_website(cmd) or self.open_app_system(cmd):
            return

        self.say("Maaf, saya belum memahami perintah itu. Katakan bantuan untuk melihat yang bisa saya lakukan.")

    def smart_search_and_open(self, cmd):
        is_journal = any(w in cmd for w in ["jurnal", "journal", "paper", "skripsi", "ilmiah", "scholar"])
        is_article = any(w in cmd for w in ["artikel", "berita", "blog", "panduan", "materi"])
        is_direct_open = any(w in cmd for w in ["dan buka", "lalu buka", "langsung buka", "buka salah satu", "buka yang pertama"])

        if is_journal or is_article or is_direct_open or cmd.startswith(("buka jurnal", "buka artikel", "cari jurnal", "cari artikel")):
            clean_q = re.sub(
                r"\b(cari|carikan|buka|tolong|dan|lalu|langsung|satu|salah|artikel|jurnal|journal|paper|ilmiah|scholar|tentang|mengenai)\b",
                " ", cmd, flags=re.IGNORECASE
            )
            clean_q = re.sub(r"\s+", " ", clean_q).strip()

            if not clean_q:
                return False

            if is_journal:
                self.say(f"Mencari dan membuka jurnal tentang {clean_q}.")
                search_url = f"https://scholar.google.com/scholar?q={urllib.parse.quote(clean_q)}"
            else:
                self.say(f"Mencari dan membuka {clean_q}.")
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(clean_q)}"

            try:
                html = http_get(search_url, timeout=5).decode("utf-8", errors="ignore")
                if is_journal:
                    links = re.findall(r'<h3 class="gs_rt"><a href="(https?://[^"]+)"', html)
                else:
                    links = re.findall(r'/url\?q=(https?://[^&"]+)', html)
                    links = [l for l in links if "google.com" not in l and "youtube.com" not in l]

                if links:
                    top_link = urllib.parse.unquote(links[0])
                    webbrowser.open(top_link)
                    return True
            except Exception as err:
                print("Gagal mengambil link teratas:", err)

            webbrowser.open(search_url)
            return True

        return False

    def play_youtube_direct(self, cmd):
        clean_query = re.sub(
            r"\b(buka|youtube|lalu|dan|cari|lagu|video|putar|putarkan|dengarkan|play|di|tolong|kan|minta)\b",
            " ", cmd, flags=re.IGNORECASE
        )
        clean_query = re.sub(r"\s+", " ", clean_query).strip()

        if not clean_query:
            self.say("Lagu atau video apa yang ingin kamu putar?")
            return

        self.say(f"Memutar {clean_query} di YouTube.")

        if HAS_WHATKIT:
            try:
                pywhatkit.playonyt(clean_query)
                return
            except Exception as e:
                print("PyWhatKit error:", e)

        try:
            search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(clean_query)
            html = http_get(search_url).decode("utf-8")
            video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", html)
            if video_ids:
                webbrowser.open(f"https://www.youtube.com/watch?v={video_ids[0]}")
                return
        except Exception as err:
            print("Gagal mengambil URL video langsung:", err)

        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(clean_query))

    def open_app_system(self, cmd):
        clean_name = re.sub(
            r"\b(buka|jalankan|nyalakan|tampilkan|aplikasi|program|software)\b",
            "", cmd, flags=re.IGNORECASE
        ).strip()

        if not clean_name:
            return False

        if clean_name in APP_OPEN_MAP:
            try:
                os.startfile(APP_OPEN_MAP[clean_name])
                self.say(f"Membuka {clean_name}.")
                return True
            except Exception:
                pass

        if app_scanner.launch(clean_name):
            self.say(f"Membuka {clean_name}.")
            return True

        if cmd.startswith("buka"):
            self.say(f"Aplikasi {clean_name} tidak ditemukan di komputer Anda.")
            return True

        return False

    def search_google(self, cmd):
        query = re.sub(r"^\s*(cari di google|cari di internet|cari)\s*", "", cmd).strip()
        if not query:
            self.say("Apa yang ingin kamu cari?")
            return
        self.say(f"Mencari {query} di Google.")
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))

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
        if not m:
            return
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
            self.say("Sebutkan isi catatan setelah kata catat.")
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


# =========================================================
# MODUL EKSTENSI REGISTRY
# =========================================================

REGISTRY = []

def cmd(*triggers, rx=None):
    def deco(fn):
        REGISTRY.append((triggers, re.compile(rx) if rx else None, fn))
        return fn
    return deco

def dispatch_features(b, c):
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

    for triggers, rx, fn in REGISTRY:
        m = rx.search(c) if rx else None
        if m or any(t in c for t in triggers):
            try:
                if fn(b, c, m) is not False:
                    return True
            except (urllib.error.URLError, socket.timeout):
                b.say("Koneksi internet bermasalah.")
                return True
            except Exception as error:
                b.app.log("sys", f"Fitur gagal ({fn.__name__}): {error}")
                b.say("Maaf, fitur itu gagal dijalankan.")
                return True
    return False

def set_clipboard(text):
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:RAY_TXT"],
                   env=dict(os.environ, RAY_TXT=text), creationflags=NOWIN)

def keys(*k):
    pyautogui.hotkey(*k) if len(k) > 1 else pyautogui.press(k[0])

# ---------- REGISTRASI PERINTAH TUTUP APLIKASI / WINDOWS ----------

@cmd("tutup", "keluar dari", rx=r"\b(tutup|close|matikan|hentikan)\s+(.+)")
def h_close_app(b, c, m):
    if not m:
        return False
    
    raw_target = m.group(2).lower().strip()
    target = re.sub(r"\b(aplikasi|program|software|jendela)\b", "", raw_target).strip()
    if not target:
        target = raw_target

    if target in ("tab", "halaman", "tab browser"):
        pyautogui.hotkey("ctrl", "w")
        b.say("Menutup tab.")
        return True

    if target in ("jendela aktif", "layar ini", "ini"):
        pyautogui.hotkey("alt", "f4")
        b.say("Menutup jendela.")
        return True

    targets_exe = []
    for alias, exes in APP_PROCESS_MAP.items():
        if alias in target or target in alias:
            targets_exe.extend(exes)

    closed = False

    if targets_exe:
        for exe in targets_exe:
            try:
                res = subprocess.run(
                    ["taskkill", "/F", "/IM", exe], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    creationflags=NOWIN
                )
                if res.returncode == 0:
                    closed = True
            except Exception:
                pass

    if not closed and psutil:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                p_name = proc.info['name'].lower()
                if targets_exe and p_name in targets_exe:
                    proc.terminate()
                    closed = True
                elif not targets_exe and target in p_name:
                    proc.terminate()
                    closed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    display_name = target if target else raw_target
    if closed:
        b.say(f"Berhasil menutup {display_name}.")
    else:
        b.say(f"Aplikasi {display_name} tidak ditemukan atau tidak sedang berjalan.")
    return True

@cmd("mulai rekam layar", "rekam layar", "mulai rekaman")
def h_start_screen_rec(b, c, m):
    if not HAS_CV2:
        b.say("Fitur rekam layar memerlukan pustaka OpenCV (pip install opencv-python).")
        return
    if screen_recorder.start():
        b.say("Mulai merekam layar. Katakan stop rekam layar untuk berhenti.")
    else:
        b.say("Rekam layar sudah berjalan.")

@cmd("stop rekam layar", "berhenti rekam layar", "hentikan rekam layar", "stop rekaman")
def h_stop_screen_rec(b, c, m):
    filepath = screen_recorder.stop()
    if filepath and os.path.exists(filepath):
        abs_path = os.path.abspath(filepath)
        folder_path = os.path.dirname(abs_path)
        
        b.app.log("sys", f"Tersimpan: {abs_path}")
        b.say("Rekam layar dihentikan. Membuka folder hasil rekaman.")
        
        try:
            os.startfile(folder_path)
        except Exception:
            pass
    else:
        b.say("Tidak ada rekam layar yang sedang berjalan atau file gagal disimpan.")

@cmd("ambil foto", "foto selfie", "potret aku")
def h_photo(b, c, m):
    if not HAS_CV2:
        b.say("Fitur kamera membutuhkan modul opencv-python.")
        return
    cam = cv2.VideoCapture(0)
    ok, frame = cam.read()
    cam.release()
    if not ok:
        b.say("Kamera tidak bisa diakses.")
        return
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    path = os.path.join(PHOTO_FOLDER, datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg"))
    cv2.imwrite(path, frame)
    b.app.log("sys", f"Tersimpan: {os.path.abspath(path)}")
    b.say("Foto berhasil diambil.")

@cmd("mulai mendikte", "mode dikte", "mulai dikte")
def h_dictate_start(b, c, m):
    b.mode = "dictation"
    b.say("Mode dikte aktif. Katakan selesai mendikte untuk berhenti.")

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
            set_clipboard(part.strip()[0].upper() + part.strip()[1:] + " ")
            time.sleep(0.1)
            keys("ctrl", "v")
        if i < len(parts) - 1:
            keys("enter")
    return True

@cmd("info sistem", "penggunaan cpu", "penggunaan ram", "sisa penyimpanan")
def h_sys(b, c, m):
    if not psutil:
        b.say("Fitur sistem memerlukan psutil.")
        return
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    msg = f"CPU {cpu:.0f} persen. RAM {ram.percent:.0f} persen. Sisa penyimpanan {disk.free / 1e9:.0f} GB."
    b.app.log("sys", msg)
    b.say(msg)


# =========================================================
# ANTARMUKA GUI (TKINTER)
# =========================================================

class RayAssistantApp:
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

        root.title("Ray Assistant")
        root.geometry("980x660")
        root.minsize(860, 580)
        root.configure(bg=BG)
        self.speaker.ready.wait(5)
        self._build()
        self.log("sys", "Ray Assistant aktif dan siap. Katakan 'bantuan' untuk melihat daftar perintah.")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick()

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                        arrowcolor=TEXT, bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED)

        left = tk.Frame(self.root, bg=BG, width=320)
        left.pack(side="left", fill="y", padx=(24, 12), pady=20)
        left.pack_propagate(False)
        right = tk.Frame(self.root, bg=PANEL)
        right.pack(side="right", fill="both", expand=True, padx=(12, 24), pady=20)

        tk.Label(left, text="Ray Assistant", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 22)).pack(anchor="w")
        tk.Label(left, text="Asisten Suara Pribadi", bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w")

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
                         bg=PANEL, troughcolor=PANEL2, activebackground=AQUA, highlightthickness=0, bd=0, sliderrelief="flat")
            s.set(init)
            s.pack(fill="x", pady=(0, 6))

        head = tk.Frame(right, bg=PANEL)
        head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text="Percakapan", bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(side="left")
        self._button(head, "Bersihkan", self.clear_chat).pack(side="right")

        body = tk.Frame(right, bg=PANEL)
        body.pack(fill="both", expand=True, padx=18)
        self.chat = tk.Text(body, bg=PANEL, fg=TEXT, relief="flat", wrap="word", state="disabled",
                            font=("Segoe UI", 11), padx=4, pady=6, highlightthickness=0)
        bar = ttk.Scrollbar(body, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("user_name", foreground=SKY, font=("Segoe UI Semibold", 10))
        self.chat.tag_configure("ray_name", foreground=AQUA, font=("Segoe UI Semibold", 10))
        self.chat.tag_configure("user", foreground=TEXT)
        self.chat.tag_configure("ray", foreground=TEXT)
        self.chat.tag_configure("sys", foreground=MUTED, font=("Segoe UI", 10, "italic"))

        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x", padx=18, pady=16)
        self.entry = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 12))
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

    def log(self, kind, text):
        self.ui.put(("log", kind, text))

    def _append(self, kind, text):
        t = self.chat
        t.configure(state="normal")
        if kind == "sys":
            t.insert("end", f"{text}\n\n", "sys")
        else:
            stamp = datetime.datetime.now().strftime("%H:%M")
            display_name = "Kamu" if kind == "user" else "Ray Assistant"
            tag_prefix = "user" if kind == "user" else "ray"
            t.insert("end", f"{display_name}  {stamp}\n", tag_prefix + "_name")
            t.insert("end", f"{text}\n\n", tag_prefix)
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
        except queue.Empty:
            pass

        state = "off" if not self.active.is_set() else ("speaking" if self.speaker.busy else self.state)
        self.t += 0.033
        self.smooth += (self.level - self.smooth) * 0.25
        self.draw_orb(state)
        self.status.configure(text=STATE_TEXT[state], fg=STATE_COLOR[state] if state != "off" else MUTED)
        self.root.after(33, self.tick)

    def set_active(self, on):
        if on == self.active.is_set():
            return
        if on:
            self.active.set()
            self.gen += 1
            greeting = "Ray Assistant siap mendengarkan."
            self.log("ray", greeting)
            self.speaker.say(greeting, wait=False)
            threading.Thread(target=self.listen_loop, args=(self.gen,), daemon=True).start()
        else:
            self.active.clear()
            self.gen += 1
            self.speaker.stop()
            screen_recorder.stop()
            self.level = 0.0
            self.log("sys", "Ray Assistant dimatikan.")
        self.draw_switch()

    def say(self, text):
        self.log("ray", text)
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
            self.log("sys", "Nyalakan Ray Assistant terlebih dahulu.")
            return
        threading.Thread(target=self.brain.handle, args=(text,), daemon=True).start()

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
            self.log("sys", "Koneksi internet diperlukan.")
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
                self.log("sys", f"Kesalahan mikrofon: {error}")
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
        screen_recorder.stop()
        self.root.destroy()


# =========================================================
# MENJALANKAN APLIKASI
# =========================================================

if __name__ == "__main__":
    window = tk.Tk()
    app = RayAssistantApp(window)
    window.mainloop()