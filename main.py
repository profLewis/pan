"""
WAV file browser & player for SEENGREAT Pico Expansion Mini Rev 2.1
Reads the SD card, lists available WAV files, and plays them on demand.

SD card wiring (SPI1):
    SCK  -> GP10
    MOSI -> GP11
    MISO -> GP12
    CS   -> GP13

Audio output (PWM):
    Left  -> GP18
    Right -> GP19  (3.5mm jack)
"""

import machine
import os
import struct
import json

from sdcard import SDCard
from audio import play_wav, get_volume, set_volume


# --- SD card pin config (SPI1 on the Pico Expansion Mini) ---
SPI_ID   = 1
PIN_SCK  = 10
PIN_MOSI = 11
PIN_MISO = 12
PIN_CS   = 13
MOUNT    = "/sd"


def mount_sd():
    """Initialise SPI1, create SDCard driver, and mount at /sd."""
    spi = machine.SPI(
        SPI_ID,
        baudrate=1_000_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(PIN_SCK),
        mosi=machine.Pin(PIN_MOSI),
        miso=machine.Pin(PIN_MISO),
    )
    cs = machine.Pin(PIN_CS, machine.Pin.OUT)
    sd = SDCard(spi, cs)
    vfs = os.VfsFat(sd)
    os.mount(vfs, MOUNT)
    print("SD card mounted at", MOUNT)
    return sd


def parse_wav_header(path):
    """Read the RIFF/WAV header and return a dict of audio properties."""
    info = {}
    try:
        with open(path, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12:
                return None
            if riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return None
            info["file_size"] = struct.unpack("<I", riff[4:8])[0] + 8

            # walk sub-chunks looking for 'fmt '
            while True:
                chunk_hdr = f.read(8)
                if len(chunk_hdr) < 8:
                    break
                chunk_id = chunk_hdr[0:4]
                chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]

                if chunk_id == b"fmt ":
                    fmt = f.read(chunk_size)
                    audio_fmt = struct.unpack("<H", fmt[0:2])[0]
                    info["format"] = "PCM" if audio_fmt == 1 else str(audio_fmt)
                    info["channels"] = struct.unpack("<H", fmt[2:4])[0]
                    info["sample_rate"] = struct.unpack("<I", fmt[4:8])[0]
                    info["byte_rate"] = struct.unpack("<I", fmt[8:12])[0]
                    info["bits_per_sample"] = struct.unpack("<H", fmt[14:16])[0]
                elif chunk_id == b"data":
                    info["data_bytes"] = chunk_size
                    break  # no need to read further
                else:
                    f.read(chunk_size)  # skip unknown chunk
    except Exception as e:
        print("  Warning: could not parse", path, "->", e)
        return None

    if "sample_rate" in info and "byte_rate" in info and info["byte_rate"] > 0:
        data = info.get("data_bytes", info["file_size"])
        info["duration_s"] = data / info["byte_rate"]
    return info


def fmt_duration(secs):
    """Return a human-friendly duration string."""
    m = int(secs) // 60
    s = secs - m * 60
    return "{}m {:04.1f}s".format(m, s) if m else "{:.1f}s".format(s)


def find_wav_files(base):
    """Recursively find all .wav files under base."""
    wavs = []
    try:
        entries = os.listdir(base)
    except OSError:
        return wavs
    for name in sorted(entries):
        full = base + "/" + name
        try:
            if os.stat(full)[0] & 0x4000:  # directory
                wavs.extend(find_wav_files(full))
            elif name.lower().endswith(".wav"):
                wavs.append(full)
        except OSError:
            pass
    return wavs


def load_config(path):
    """Try to load a JSON config file from the SD card."""
    for name in ("config.json", "config.txt", "CONFIG.JSON", "CONFIG.TXT"):
        try:
            full = path + "/" + name
            with open(full, "r") as f:
                data = f.read()
            print("Config found:", full)
            try:
                cfg = json.loads(data)
                return cfg
            except ValueError:
                # not valid JSON - just print raw contents
                print("--- config contents ---")
                print(data)
                print("-----------------------")
                return data
        except OSError:
            continue
    print("No config file found on SD card.")
    return None


def show_list(wavs):
    """Print the numbered WAV file listing."""
    print()
    print("Available WAV files:")
    print()
    for i, path in enumerate(wavs, 1):
        display = path[len(MOUNT) + 1:]
        info = parse_wav_header(path)
        if info:
            dur = fmt_duration(info.get("duration_s", 0))
            ch = "stereo" if info.get("channels", 1) == 2 else "mono"
            sr = info.get("sample_rate", 0)
            warn = " *" if sr != 22050 else ""
            print(
                "  {:>2}. {:<30s}  {:>5}Hz  {}bit  {}  {}{}".format(
                    i,
                    display,
                    sr,
                    info.get("bits_per_sample", "?"),
                    ch,
                    dur,
                    warn,
                )
            )
        else:
            print("  {:>2}. {:<30s}  (unable to read header)".format(i, display))
    print("  (* = not 22050Hz — re-encode for best playback quality)")
    print()


def main():
    print()
    print("=" * 44)
    print("  WAV Player  -  Pico Expansion Mini 2.1")
    print("=" * 44)

    # 1. Mount SD card
    try:
        mount_sd()
    except OSError as e:
        print("ERROR: Could not mount SD card:", e)
        print("Check that the card is inserted and formatted as FAT.")
        return

    # 2. Read config
    print()
    cfg = load_config(MOUNT)

    # 3. Scan for WAV files
    print()
    print("Scanning for WAV files...")
    wavs = find_wav_files(MOUNT)

    if not wavs:
        print("No .wav files found on the SD card.")
        return

    print("Found {} WAV file(s).".format(len(wavs)))

    # 4. Interactive playback loop
    show_list(wavs)

    while True:
        vol = get_volume()
        vol_bar = "#" * vol + "." * (10 - vol)
        print("[vol {}/10 {}]".format(vol, vol_bar))
        print("Enter: number to play, +/- volume, 'l' list, 'q' quit")
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not choice:
            continue

        ch = choice.lower()

        if ch == "q":
            break

        if ch == "l":
            show_list(wavs)
            continue

        if ch == "+":
            v = set_volume(get_volume() + 1)
            print("  Volume: {}/10".format(v))
            continue

        if ch == "-":
            v = set_volume(get_volume() - 1)
            print("  Volume: {}/10".format(v))
            continue

        if ch.startswith("v"):
            # 'v7' or 'v 7' sets volume directly
            try:
                v = set_volume(int(choice[1:].strip()))
                print("  Volume: {}/10".format(v))
            except ValueError:
                print("  Usage: v0 .. v10")
            continue

        # try to parse as a number
        try:
            num = int(choice)
        except ValueError:
            print("  Invalid input.")
            continue

        if num < 1 or num > len(wavs):
            print("  Pick a number between 1 and {}.".format(len(wavs)))
            continue

        path = wavs[num - 1]
        display = path[len(MOUNT) + 1:]
        print()
        print(">> Playing: {}".format(display))
        play_wav(path)
        print()

    print("Goodbye.")


main()
