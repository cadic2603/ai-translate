---
description: Przechwytuj dźwięk systemowy na Linuksie, macOS i Windows dla strony Live AI Translate — tłumacz dowolny dźwięk odtwarzany na komputerze w czasie rzeczywistym.
---

# Przechwytywanie dźwięku systemowego (Live)

Strona **[Live Translation](../features/live-translation.md)** może
przechwytywać **dźwięk systemowy** (wszystko, co odtwarza się na
twoich głośnikach), więc możesz tłumaczyć / dodawać napisy do
dowolnych mediów — rozmowy Zoom, YouTube, Netflix, gry, dźwięki
systemowe.

W **Settings → Live → Audio source** (lub combo na górze strony
Live) wybierz:

- **Microphone** — tylko twój mikrofon
- **System audio** — tylko to, co odtwarza się na twoich głośnikach
- **Both** — oba zmiksowane (dobre do narracji nad mediami lub
  przechwytywania spotkań hybrydowych)

Gdy wybierasz **System audio** lub **Both**, aplikacja kieruje do
odpowiedniego backendu przechwytywania dla twojego OS. Pojawia się
inline banner ostrzeżenia z klikalnymi linkami instalacyjnymi,
jeśli wymagania OS nie są spełnione, więc nie musisz rozpoczynać
sesji, aby dowiedzieć się, że czegoś brakuje.

## Linux (PulseAudio / PipeWire)

Działa out of the box na każdej nowoczesnej dystrybucji.

Aplikacja używa `parec` (PulseAudio Recorder), aby tap **monitor
source** twojego domyślnego sinka. Shim kompatybilności PulseAudio
PipeWire czyni to przezroczystym — nie potrzebujesz surowego
PulseAudio.

```bash
parec --version    # powinien coś wydrukować
```

Jeśli `parec` brakuje, banner ostrzeżenia wykrywa menedżer pakietów
twojej dystrybucji i wstawia dokładne polecenie instalacji — na
przykład:

> Przechwytywanie dźwięku systemowego potrzebuje PulseAudio lub
> PipeWire — uruchom `sudo apt-get install pulseaudio`.

Wykrywany na apt-get / dnf / pacman / zypper / apk; możesz
skopiować-wkleić polecenie bezpośrednio do terminala.

## macOS

CoreAudio nie eksponuje natywnie dźwięku systemowego, więc
potrzebujesz **wirtualnego urządzenia loopback** — zainstaluj jedno
z:

- **[BlackHole](https://existential.audio/blackhole/)** — darmowe, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — płatne, dopracowane GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — stara darmowa opcja
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — płatne

Aplikacja auto-wykrywa którekolwiek z nich przez
`ffmpeg -f avfoundation -list_devices` i używa pierwszego dopasowania.
Nie ma potrzeby ustawiania loopback jako twojego domyślnego wyjścia
/ wejścia — przechwytywanie dzieje się bezpośrednio przez backend
avfoundation `ffmpeg`.

Po instalacji po prostu wybierz **System audio** w combo strony
Live, a banner ostrzeżenia znika.

## Windows

Natywny — **nie potrzebujesz dodatkowego oprogramowania** w
większości przypadków.

Aplikacja rozmawia bezpośrednio z **WASAPI loopback** przez pakiet
Python [`soundcard`](https://github.com/bastibe/SoundCard)
(instalowany automatycznie z aplikacją na Windows). To to samo
natywne API loopback, którego używają aplikacje desktopowe Tauri /
Rust; przechwytuje domyślne wyjście głośnika bez wirtualnego kabla.

Jeśli z jakiegoś powodu WASAPI loopback nie jest dostępny (starsze
wersje Windows, nietypowy sterownik audio), aplikacja fallbackuje
na `ffmpeg -f dshow` przeciwko wirtualnemu urządzeniu DirectShow
loopback. Wybierz jedno z:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — darmowe, dostarcza `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — darmowe, dostępne jako `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — stara opcja on-board, często domyślnie wyłączona

Aplikacja sonduje je w kolejności i używa pierwszego obecnego.

## Dlaczego "Both" wychwytuje twój głos AND dźwięk systemowy

W trybie **Both** aplikacja otwiera DWA strumienie przechwytywania
równolegle — twój mikrofon przez `sounddevice`, dźwięk systemowy
przez backend specyficzny dla OS powyżej — i miksuje je z
ziarnistością bloku próbki. To właściwy tryb do narracji nad
filmem lub przechwytywania obu stron spotkania hybrydowego (twój
głos plus uczestnicy na głośnikach).

> **Wskazówka:** jeśli słyszysz echo lub otrzymujesz duplikaty
> napisów, masz dźwięk systemowy idący przez twój mikrofon
> (głośne głośniki → mikrofon je wychwytuje). Przełącz na samo
> **System audio** lub użyj słuchawek.

## Rozwiązywanie problemów

| Symptom | Prawdopodobna przyczyna |
|---|---|
| Strona Live startuje, ale brak napisów | Wybrano złe źródło audio lub twój domyślny mikrofon jest wyciszony |
| Napisy dla twojego głosu, ale nie dla wideo YouTube | Wymóg dźwięku systemowego nie jest zainstalowany (banner powinien pokazać instrukcje instalacji) |
| Napisy dwukrotnie (echo) | Tryb "Both" wychwytuje dźwięk systemowy dwukrotnie — raz z głośników przez mikrofon, raz przez loopback. Przełącz na samo System audio lub użyj słuchawek |
| Banner pozostaje widoczny po zainstalowaniu brakującego oprogramowania | Przełącz karty i wróć — banner sprawdza ponownie przy pokazaniu strony |
| macOS: BlackHole zainstalowany, ale banner nadal się pojawia | Potwierdź, że BlackHole jest na liście urządzeń audio `ffmpeg -f avfoundation -list_devices true -i ""`; aplikacja musi go tam zobaczyć |
| Windows: WASAPI loopback zawodzi pomimo braku błędu | Spróbuj zainstalować VB-Audio Virtual Cable jako fallback; starsze wersje Windows lub niektóre sterowniki audio nie eksponują loopback przez `soundcard` |
