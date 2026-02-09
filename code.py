"""
WAV player & hit sensor for SEENGREAT Pico Expansion Mini Rev 2.1
CircuitPython version — polyphonic WAV playback via audiomixer.

SD card (SPI1): GP10-GP12, CS=GP15
Audio PWM:      GP18 (L/buzzer), GP19 (R/jack)
Sensor:         GP2  (second Grove, 10K pull-down)
"""

import board
import busio
import sdcardio
import storage
import os
import json
import time

from audio_player import AudioPlayer
from melody import play_tetris, play_in_the_mood
from sensor import HitSensor, MPR121Sensor

MOUNT = "/sd"

# Default chromatic note mapping for MPR121 channels 0-11 (A4 through G#5)
DEFAULT_NOTES = [
    "A4", "As4", "B4", "C5", "Cs5", "D5",
    "Ds5", "E5", "F5", "Fs5", "G5", "Gs5",
]


def mount_sd():
    try:
        os.mkdir(MOUNT)
    except OSError:
        pass  # already exists
    spi = busio.SPI(board.GP10, MOSI=board.GP11, MISO=board.GP12)
    sd = sdcardio.SDCard(spi, board.GP15)
    vfs = storage.VfsFat(sd)
    storage.mount(vfs, MOUNT)
    print("SD card mounted at", MOUNT)


def load_config():
    for name in ("config.json", "CONFIG.JSON"):
        try:
            with open(MOUNT + "/" + name, "r") as f:
                cfg = json.loads(f.read())
            print("Config found:", name)
            print("  sensor:      {}".format(cfg.get("sensor", "digital")))
            print("  hit_wav:     {}".format(cfg.get("hit_wav", "(not set)")))
            print("  volume:      {}".format(cfg.get("volume", "(default)")))
            print("  cooldown_ms: {}".format(cfg.get("cooldown_ms", "(default)")))
            return cfg
        except (OSError, ValueError):
            continue
    print("No config.json found on SD card.")
    return {}


def find_wav_files(base):
    wavs = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return wavs
    for name in entries:
        full = base + "/" + name
        try:
            stat = os.stat(full)
            if stat[0] & 0x4000:
                wavs.extend(find_wav_files(full))
            elif name.lower().endswith(".wav"):
                wavs.append(full)
        except OSError:
            pass
    return wavs


def show_list(wavs):
    print()
    print("Available WAV files:")
    print()
    for i, path in enumerate(wavs, 1):
        display = path[len(MOUNT) + 1:]
        print("  {:>2}. {}".format(i, display))
    print()


def resolve_hit_wav(cfg, wavs):
    hit_name = cfg.get("hit_wav")
    if not hit_name:
        return None
    for w in wavs:
        if w.endswith("/" + hit_name) or w == MOUNT + "/" + hit_name:
            return w, hit_name
    print("  WARNING: hit_wav '{}' not found on SD card.".format(hit_name))
    return None


def sensor_mode(cfg, wavs, player):
    sensor_type = cfg.get("sensor", "digital")
    cooldown = cfg.get("cooldown_ms", 2000)
    use_mpr121 = sensor_type == "mpr121"

    # Build channel -> WAV path mapping
    channel_wav = {}

    if use_mpr121:
        custom = cfg.get("mpr121_channels", {})
        for ch in range(12):
            ch_str = str(ch)
            if ch_str in custom:
                wav_name = custom[ch_str]
            else:
                wav_name = DEFAULT_NOTES[ch] + ".wav"
            # Find WAV on SD card
            for w in wavs:
                if w.endswith("/" + wav_name) or w == MOUNT + "/" + wav_name:
                    channel_wav[ch] = w
                    break
        if not channel_wav:
            print("  No WAV files matched for MPR121 channels.")
            return
        sensor = MPR121Sensor(cooldown_ms=cooldown)
    else:
        result = resolve_hit_wav(cfg, wavs)
        if result is None:
            print("  Set \"hit_wav\" in config.json to a WAV filename.")
            show_list(wavs)
            return
        wav_path, display = result
        channel_wav[0] = wav_path
        sensor = HitSensor(cooldown_ms=cooldown)

    # Status banner
    print()
    print("-" * 44)
    print("  SENSOR MODE (polyphonic)")
    print("  Sensor:   {}".format(sensor_type))
    if use_mpr121:
        print("  Channels: {} mapped".format(len(channel_wav)))
        for ch in sorted(channel_wav):
            name = channel_wav[ch][len(MOUNT) + 1:]
            print("    ch {:>2} -> {}".format(ch, name))
    else:
        print("  WAV:      {}".format(display))
    print("  Volume:   {}/10".format(player.volume_int()))
    print("  Cooldown: {}ms".format(cooldown))
    print("  Voices:   {} available".format(4))
    print("-" * 44)
    print("  Waiting for hits... Ctrl+C to exit.")
    print()

    try:
        while True:
            channels = sensor.check()
            for ch in channels:
                if ch in channel_wav:
                    v = player.play_wav(channel_wav[ch])
                    name = channel_wav[ch][len(MOUNT) + 1:]
                    print("  * HIT #{} ch{} (voice {}) - {}".format(
                        sensor.count, ch, v, name))
            time.sleep(0.01)
    except KeyboardInterrupt:
        print()
        print()
        print("  Exited sensor mode. {} hit(s).".format(sensor.count))
        print()
    finally:
        sensor.deinit()


def main():
    print()
    print("=" * 44)
    print("  WAV Player  -  Pico Expansion Mini 2.1")
    print("  CircuitPython  |  Polyphonic")
    print("=" * 44)

    # 1. Create audio player
    player = AudioPlayer()

    # 2. Mount SD card (before melody so WAV samples are available)
    sd_ok = False
    try:
        mount_sd()
        sd_ok = True
    except Exception as e:
        print("WARNING: Could not mount SD card:", e)

    # 3. Startup jingle — alternate between Tetris and In the Mood
    import microcontroller
    boot_count = microcontroller.nvm[0]
    microcontroller.nvm[0] = (boot_count + 1) % 256
    print()
    if boot_count % 2 == 0:
        play_tetris(player, MOUNT if sd_ok else None)
    else:
        play_in_the_mood(player, MOUNT if sd_ok else None)

    # 4. Load config
    cfg = {}
    if sd_ok:
        print()
        cfg = load_config()
        if "volume" in cfg:
            player.set_volume_int(cfg["volume"])

    # 5. Scan for WAV files
    wavs = []
    if sd_ok:
        print()
        print("Scanning for WAV files...")
        wavs = find_wav_files(MOUNT)
        if not wavs:
            print("No .wav files found.")
        else:
            print("Found {} WAV file(s).".format(len(wavs)))

    # 6. Interactive loop
    if wavs:
        show_list(wavs)

    while True:
        vi = player.volume_int()
        bar = "#" * vi + "." * (10 - vi)
        print("[vol {}/10 {}]".format(vi, bar))
        print("Enter: number, +/- vol, 's' sensor, 'l' list, 'q' quit")
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

        if ch == "s":
            sensor_mode(cfg, wavs, player)
            continue

        if ch == "+":
            player.set_volume_int(player.volume_int() + 1)
            print("  Volume: {}/10".format(player.volume_int()))
            continue

        if ch == "-":
            player.set_volume_int(player.volume_int() - 1)
            print("  Volume: {}/10".format(player.volume_int()))
            continue

        if ch.startswith("v"):
            try:
                player.set_volume_int(int(choice[1:].strip()))
                print("  Volume: {}/10".format(player.volume_int()))
            except ValueError:
                print("  Usage: v0 .. v10")
            continue

        try:
            num = int(choice)
        except ValueError:
            print("  Invalid input.")
            continue

        if num < 1 or num > len(wavs):
            print("  Pick 1-{}.".format(len(wavs)))
            continue

        path = wavs[num - 1]
        display = path[len(MOUNT) + 1:]
        v = player.play_wav(path)
        print("  Playing {} on voice {}".format(display, v))

    player.deinit()
    print("Goodbye.")


main()
