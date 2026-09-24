# WhyBeatCut

**Drop a song in a folder, get a video cut on the beat. Runs by itself at startup.**

`Python` · `librosa` · `ffmpeg` · `yt-dlp` · stato: **funzionante**

Metti una canzone in una cartella e dopo circa un minuto esce un video 1920x1080 montato a tempo di musica.
Nessun editor da aprire, nessun clic.

## Cosa fa
- trova i battiti della canzone e decide dove tagliare;
- taglia **veloce dove la musica spinge, lento dove respira** (usa l'energia del brano, non solo il BPM);
- usa prima le tue clip, poi riempie con clip stock scaricate da sole sul tema che scegli;
- toglie le bande nere dalle clip e le porta tutte allo stesso formato;
- resta acceso in background e lavora ogni canzone appena arriva.

## Come funziona
```
canzone ─► librosa: parte percussiva ─► battiti + energia (RMS)
                                              │
                                              ▼
                              istanti di taglio (1, 2 o 4 battiti)
                                              │
clip tue + clip stock (yt-dlp) ─► pezzi ─► ffmpeg ─► VIDEO FATTI/
```

## Struttura
| Percorso | Cosa contiene |
|---|---|
| `beatcut.py` | tutto il programma: analisi, scelta delle clip, montaggio |
| `tema.txt` | le parole per cercare le clip stock, una per riga |
| `METTI QUI LA MUSICA/` | le canzoni da montare (mp3, wav, flac, m4a, ogg, aac) |
| `I MIEI VIDEO/` | le tue clip, facoltative, escono più spesso |
| `clip-stock/` | clip scaricate da sole; si svuota per cambiare tema |
| `VIDEO FATTI/` | i video finiti |

Le cartelle con canzoni e video non entrano nel repo.

## Come si avvia
```
pip install librosa numpy
python beatcut.py            # lavora le canzoni nuove e si ferma
python beatcut.py --guarda   # resta acceso e lavora ogni canzone appena arriva
```
Servono `ffmpeg`, `ffprobe` e `yt-dlp`: la cartella che li contiene si imposta nella variabile `BIN` in cima a
`beatcut.py`. Per farlo partire all'avvio di Windows basta un'attività nell'Utilità di pianificazione con
`--guarda`.

## Stato
Funziona. Idee per dopo: formato verticale 9:16, tagli diversi per strofa e ritornello.

## Perché è nato
Serviva un modo per montare clip a tempo con una canzone senza passare ore su un editor. Prima si è cercato un
progetto open source già pronto; poi si è scelto di scriverne uno piccolo e locale che fa una cosa sola.

---

Parte di **[WhyEcosystem 2023-2026](https://github.com/OfficialWhyEd/WhyEcosystem-2023-2026)**: il percorso di WhyEd, producer e sound engineer che costruisce sistemi AI dirigendo gli agenti.  
Costruito da WhyEd con Claude Code
