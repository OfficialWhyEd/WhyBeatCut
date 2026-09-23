"""BeatCut: metti una canzone, esce un video montato a tempo.

Cartelle:
  METTI QUI LA MUSICA/  la canzone (mp3, wav, flac, m4a)
  I MIEI VIDEO/         clip tue (facoltative): entrano nel montaggio con precedenza
  clip-stock/           clip scaricate da sole da YouTube sul tema in tema.txt
  VIDEO FATTI/          i video finiti

Uso:
  python beatcut.py            fa tutte le canzoni nuove e si ferma
  python beatcut.py --guarda   resta acceso e fa ogni canzone appena arriva
"""
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np

BASE = Path(__file__).resolve().parent
MUSICA = BASE / "METTI QUI LA MUSICA"
MIEI = BASE / "I MIEI VIDEO"
STOCK = BASE / "clip-stock"
FATTI = BASE / "VIDEO FATTI"
LAVORO = BASE / "_lavoro"
TEMA = BASE / "tema.txt"
FATTO = BASE / "_fatti.json"

BIN = Path("E:/AcapellaLab/bin")
FFMPEG = str(BIN / "ffmpeg.exe")
FFPROBE = str(BIN / "ffprobe.exe")
YTDLP = str(BIN / "yt-dlp.exe")

FPS = 30
W, H = 1920, 1080
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
MIN_CLIP_STOCK = 8


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} fallito:\n{r.stderr[-1500:]}")
    return r.stdout


def durata(path):
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def bande_nere(path, dur):
    """Ritaglio che toglie le bande nere gia' dentro la clip (letterbox)."""
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-ss", f"{dur * 0.3:.1f}", "-i", str(path), "-t", "6",
         "-vf", "cropdetect=24:2:0", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    righe = [r_ for r_ in r.stderr.splitlines() if "crop=" in r_]
    if not righe:
        return ""
    crop = righe[-1].split("crop=")[-1].strip()
    w, h = (int(v) for v in crop.split(":")[:2])
    return f"crop={crop}," if w > 200 and h > 200 else ""


def video_in(cartella):
    return sorted(p for p in cartella.glob("*") if p.suffix.lower() in VIDEO_EXT and p.stat().st_size > 100_000)


# ---------- clip stock ----------

def temi():
    if not TEMA.exists():
        TEMA.write_text(
            "# Una ricerca per riga. Le clip stock si scaricano da YouTube con queste parole.\n"
            "supercar cinematic 4k footage no copyright\n"
            "street racing night cinematic footage\n"
            "drift car cinematic 4k\n",
            encoding="utf-8",
        )
    righe = [r.strip() for r in TEMA.read_text(encoding="utf-8").splitlines()]
    return [r for r in righe if r and not r.startswith("#")]


def scarica_stock():
    if len(video_in(STOCK)) >= MIN_CLIP_STOCK:
        return
    for ricerca in temi():
        log(f"scarico clip stock: {ricerca}")
        cmd = [
            YTDLP, f"ytsearch6:{ricerca}",
            "--ffmpeg-location", str(BIN),
            "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]",
            "--match-filter", "duration > 30 & duration < 900 & !is_live",
            # solo due minuti per video: si scarica in fretta e occupa poco
            "--download-sections", "*15-135",
            "--no-playlist", "--ignore-errors", "--no-warnings",
            "-o", str(STOCK / "%(id)s.%(ext)s"),
        ]
        subprocess.run(cmd, capture_output=True)
        if len(video_in(STOCK)) >= MIN_CLIP_STOCK:
            break
    log(f"clip stock pronte: {len(video_in(STOCK))}")


# ---------- analisi della musica ----------

def tagli(audio_path):
    """Istanti di taglio (secondi): veloci dove la musica spinge, lenti dove respira."""
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    fine = len(y) / sr
    y_perc = librosa.effects.percussive(y)
    tempo, beat_frames = librosa.beat.beat_track(y=y_perc, sr=sr, units="frames")
    beats = librosa.frames_to_time(beat_frames, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    if len(beats) < 8:
        beats = np.arange(0, fine, 0.5)

    rms = librosa.feature.rms(y=y)[0]
    rms_t = librosa.times_like(rms, sr=sr)
    energia = np.interp(beats, rms_t, rms)
    energia = np.convolve(energia, np.ones(4) / 4, mode="same")
    alta, bassa = np.quantile(energia, 0.7), np.quantile(energia, 0.3)

    # passo in battute: a BPM alti un beat e' troppo corto per leggere l'immagine
    base = 2 if tempo >= 115 else 1
    punti = [0.0]
    i = 0
    while i < len(beats):
        e = energia[i]
        passo = base if e >= alta else (base * 2 if e >= bassa else base * 4)
        i += passo
        if i < len(beats) and beats[i] - punti[-1] >= 0.3:
            punti.append(float(beats[i]))
    if fine - punti[-1] < 0.5:
        punti.pop()
    punti.append(fine)
    log(f"tempo {tempo:.0f} BPM, {len(punti) - 1} tagli, {fine:.0f} s")
    return punti, fine


# ---------- montaggio ----------

class Pool:
    def __init__(self):
        self.clip = []
        for p in video_in(MIEI):
            self.clip.append({"path": p, "mio": True})
        for p in video_in(STOCK):
            self.clip.append({"path": p, "mio": False})
        for c in self.clip:
            c["dur"] = durata(c["path"])
            c["usati"] = []
            c["crop"] = bande_nere(c["path"], c["dur"]) if c["dur"] > 3 else ""
        self.clip = [c for c in self.clip if c["dur"] > 3]
        if not self.clip:
            raise RuntimeError("nessuna clip: metti video in I MIEI VIDEO o controlla la connessione")
        self.ultimo = None

    def prendi(self, lung):
        adatte = [c for c in self.clip if c["dur"] > lung + 1 and c is not self.ultimo] or self.clip
        # le clip tue escono piu' spesso di quelle stock
        pesi = [4.0 if c["mio"] else 1.0 for c in adatte]
        c = random.choices(adatte, weights=pesi)[0]
        self.ultimo = c
        margine = min(3.0, c["dur"] * 0.05)
        lo, hi = margine, max(margine, c["dur"] - lung - margine)
        for _ in range(12):
            s = random.uniform(lo, hi)
            if all(abs(s - u) > lung + 1 for u in c["usati"]):
                break
        c["usati"].append(s)
        return c["path"], s, c["crop"]


def pezzo(src, start, crop, frames, out):
    # tutti i pezzi con lo stesso formato colore, se no il video si "resetta" a ogni taglio
    vf = (f"{crop}scale={W}:{H}:force_original_aspect_ratio=increase:out_color_matrix=bt709:out_range=tv,"
          f"crop={W}:{H},fps={FPS},setsar=1,format=yuv420p,"
          f"setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv")
    run([
        FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
        "-an", "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-color_range", "tv", str(out),
    ])


def monta(audio):
    nome = audio.stem
    log(f"=== {audio.name} ===")
    scarica_stock()
    punti, fine = tagli(audio)
    pool = Pool()
    log(f"clip: {sum(c['mio'] for c in pool.clip)} tue, {sum(not c['mio'] for c in pool.clip)} stock")

    lav = LAVORO / nome
    lav.mkdir(parents=True, exist_ok=True)
    lista = []
    # i frame si contano sul totale, cosi' i tagli non scivolano mai fuori tempo
    fr = [round(t * FPS) for t in punti]
    for k in range(len(fr) - 1):
        n = fr[k + 1] - fr[k]
        if n <= 0:
            continue
        src, s, crop = pool.prendi(n / FPS)
        out = lav / f"{k:04d}.mp4"
        try:
            pezzo(src, s, crop, n, out)
        except RuntimeError:
            src, s, crop = pool.prendi(n / FPS)
            pezzo(src, s, crop, n, out)
        lista.append(out)
        if k % 20 == 0:
            log(f"  pezzo {k + 1}/{len(fr) - 1}")

    concat = lav / "lista.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in lista), encoding="utf-8")
    finale = FATTI / f"{nome}.mp4"
    run([
        FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "320k", "-t", f"{fine:.3f}", "-movflags", "+faststart", str(finale),
    ])
    for p in lista:
        p.unlink()
    concat.unlink()
    lav.rmdir()
    log(f"FATTO: {finale}")
    return finale


def stato():
    try:
        return json.loads(FATTO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def nuove():
    fatti = stato()
    for a in sorted(MUSICA.glob("*")):
        if a.suffix.lower() not in AUDIO_EXT:
            continue
        firma = f"{a.stat().st_size}-{int(a.stat().st_mtime)}"
        if fatti.get(a.name) != firma:
            yield a, firma


def giro():
    for a, firma in nuove():
        # aspetta che il file abbia finito di copiarsi
        s1 = a.stat().st_size
        time.sleep(2)
        if a.stat().st_size != s1:
            continue
        try:
            monta(a)
        except Exception as e:
            log(f"ERRORE su {a.name}: {e}")
        fatti = stato()
        fatti[a.name] = firma
        FATTO.write_text(json.dumps(fatti, indent=1), encoding="utf-8")


def main():
    for d in (MUSICA, MIEI, STOCK, FATTI, LAVORO):
        d.mkdir(exist_ok=True)
    temi()
    if "--guarda" in sys.argv:
        # parte con pythonw, senza finestra: tutto va nel log
        sys.stdout = sys.stderr = open(BASE / "_beatcut.log", "a", encoding="utf-8", buffering=1)
        log("BeatCut acceso: metti una canzone in 'METTI QUI LA MUSICA'")
        while True:
            giro()
            time.sleep(5)
    else:
        giro()


if __name__ == "__main__":
    main()
