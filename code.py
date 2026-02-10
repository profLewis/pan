"""
WAV player & hit sensor for SEENGREAT Pico Expansion Mini Rev 2.1
CircuitPython version — polyphonic WAV playback via audiomixer.

SD card (SPI1): GP10-GP12, CS=GP15
Audio PWM:      GP18 (L/buzzer), GP19 (R/jack)
I2C bus (I2C0): GP0 (SDA), GP1 (SCL) — LCD
Mux (CD74HC4067): GP2-GP5 (S0-S3), GP9 (SIG)
"""

import board
import busio
import sdcardio
import storage
import os
import json
import time

from audio_player import AudioPlayer
from melody import play_tetris
from sensor import MuxSensor

MOUNT = "/sd"


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
            print("  audio_output:{}".format(cfg.get("audio_output", "both")))
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


def _hsv_to_rgb(h, s, v):
    """Convert HSV (0-1 floats) to (R, G, B) 0-255 tuple."""
    if s == 0:
        iv = int(v * 255)
        return (iv, iv, iv)
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = int(v * (1.0 - s) * 255)
    q = int(v * (1.0 - s * f) * 255)
    t = int(v * (1.0 - s * (1.0 - f)) * 255)
    iv = int(v * 255)
    i %= 6
    if i == 0:
        return (iv, t, p)
    if i == 1:
        return (q, iv, p)
    if i == 2:
        return (p, iv, t)
    if i == 3:
        return (p, q, iv)
    if i == 4:
        return (t, p, iv)
    return (iv, p, q)


# Pre-compute a unique colour per mux channel (hue wheel, 16 steps)
CHANNEL_COLORS = [_hsv_to_rgb(ch / 16.0, 1.0, 1.0) for ch in range(16)]


def sensor_mode(cfg, wavs, player, lcd=None, pixel=None):
    cooldown = cfg.get("cooldown_ms", 200)

    # Build mux channel -> WAV mapping from config
    buttons_cfg = cfg.get("buttons", [])
    channel_wav = {}
    for btn in buttons_cfg:
        ch = btn.get("channel", 0)
        wav_name = btn.get("wav")
        if wav_name:
            for w in wavs:
                if w.endswith("/" + wav_name) or w == MOUNT + "/" + wav_name:
                    channel_wav[ch] = (w, wav_name)
                    break

    sensor = MuxSensor(cooldown_ms=cooldown)  # scan all 16 channels
    fade_until = 0  # monotonic_ns deadline for LED off

    # Show sensor mode on LCD
    if lcd:
        lcd.show("Sensor mode", "Ready")

    # Status banner
    print()
    print("-" * 44)
    print("  SENSOR MODE (mux 16ch, polyphonic)")
    if channel_wav:
        for ch in sorted(channel_wav):
            print("  ch {:>2} -> {}".format(ch, channel_wav[ch][1]))
    else:
        print("  No WAV mappings (raw scan only)")
    print("  Volume:   {}/10".format(player.volume_int()))
    print("  Cooldown: {}ms".format(cooldown))
    print("  Voices:   {} available".format(4))
    print("-" * 44)
    print("  Scanning all 16 channels... Ctrl+C to exit.")
    print()

    try:
        while True:
            now_ns = time.monotonic_ns()
            hits = sensor.check()
            for ch in hits:
                # Flash NeoPixel with channel colour
                if pixel:
                    pixel[0] = CHANNEL_COLORS[ch]
                    fade_until = now_ns + 150_000_000  # 150ms

                if ch in channel_wav:
                    wav_path, wav_name = channel_wav[ch]
                    v = player.play_wav(wav_path)
                    note = wav_name.replace(".wav", "")
                    print("  * HIT #{} ch{} (voice {}) - {}".format(
                        sensor.count, ch, v, wav_name))
                    if lcd:
                        lcd.show("ch{} = {}".format(ch, note),
                                 "Hit #{}".format(sensor.count))
                else:
                    print("  * HIT #{} ch{} (no wav)".format(
                        sensor.count, ch))
                    if lcd:
                        lcd.show("ch{}".format(ch),
                                 "Hit #{}".format(sensor.count))

            # Fade LED off after timeout
            if pixel and fade_until and now_ns >= fade_until:
                pixel[0] = (0, 0, 0)
                fade_until = 0

            time.sleep(0.01)
    except KeyboardInterrupt:
        print()
        print()
        print("  Exited sensor mode. {} hit(s).".format(sensor.count))
        print()
    finally:
        if pixel:
            pixel[0] = (0, 0, 0)
        sensor.deinit()


def main():
    print()
    print("=" * 44)
    print("  WAV Player  -  Pico Expansion Mini 2.1")
    print("  CircuitPython  |  Polyphonic")
    print("=" * 44)

    # 0. NeoPixel on GP22 (used for melody + hit feedback)
    pixel = None
    try:
        import neopixel
        pixel = neopixel.NeoPixel(board.GP22, 1, brightness=0.3, auto_write=True)
        pixel[0] = (0, 0, 0)
    except Exception:
        pass

    # 1. Mount SD card and load config first (needed for audio output setting)
    sd_ok = False
    try:
        mount_sd()
        sd_ok = True
    except Exception as e:
        print("WARNING: Could not mount SD card:", e)

    cfg = {}
    if sd_ok:
        print()
        cfg = load_config()

    # 2. Initialize LCD (Grove 16x2 on GP0/GP1)
    display = None
    try:
        from lcd import LCD
        _lcd_i2c = busio.I2C(board.GP1, board.GP0)
        display = LCD(_lcd_i2c)
        print("  LCD: detected on GP0/GP1")
        # Show welcome text from SD card
        if sd_ok:
            try:
                with open(MOUNT + "/welcome.txt", "r") as f:
                    lines = f.read().strip().split("\n")
                display.show(
                    lines[0] if len(lines) > 0 else "",
                    lines[1] if len(lines) > 1 else "",
                )
                time.sleep(2)
            except OSError:
                display.show("Pan Player", "Starting...")
                time.sleep(1)
        else:
            display.show("Pan Player", "No SD card")
            time.sleep(1)
    except Exception as e:
        print("  LCD: not found ({})".format(e))

    # 3. Create audio player (auto-detect: try I2S, fall back to buzzer)
    audio_out = cfg.get("audio_output", "auto")
    player = AudioPlayer(output=audio_out)
    print("  Audio output: {}".format(player.output))
    if "volume" in cfg:
        player.set_volume_int(cfg["volume"])

    # 4. Startup jingle (2x speed)
    print()
    play_tetris(player, MOUNT if sd_ok else None, lcd=display, speed=2.0,
                pixel=pixel)

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

    # 6. Go straight into sensor mode, then fall through to interactive loop
    if wavs:
        sensor_mode(cfg, wavs, player, lcd=display, pixel=pixel)
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
            sensor_mode(cfg, wavs, player, lcd=display, pixel=pixel)
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
