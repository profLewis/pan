"""
Melody player for SEENGREAT Pico Expansion Mini.
Plays startup melodies using WAV note samples from SD card,
with synthio fallback if samples are unavailable.
"""

import time
import audiocore

# Durations
_Q = 400    # quarter at ~150 BPM
_E = 200    # eighth
_DQ = 600   # dotted quarter
_S = 100    # sixteenth

# Tetris Theme A (Korobeiniki)
# (note_name, duration_ms)  — None = rest
TETRIS_THEME = [
    ("E5", _Q), ("B4", _E), ("C5", _E),
    ("D5", _Q), ("C5", _E), ("B4", _E),
    ("A4", _Q), ("A4", _E), ("C5", _E),
    ("E5", _Q), ("D5", _E), ("C5", _E),
    ("B4", _DQ), ("C5", _E),
    ("D5", _Q), ("E5", _Q),
    ("C5", _Q), ("A4", _Q),
    ("A4", _Q),
    (None, _Q),
    ("D5", _DQ), ("F5", _E),
    ("A5", _Q), ("G5", _E), ("F5", _E),
    ("E5", _DQ), ("C5", _E),
    ("E5", _Q), ("D5", _E), ("C5", _E),
    ("B4", _Q), ("B4", _E), ("C5", _E),
    ("D5", _Q), ("E5", _Q),
    ("C5", _Q), ("A4", _Q),
    ("A4", _Q),
]

# Note frequencies for synthio fallback
FREQ = {
    "A4": 440, "As4": 466, "B4": 494,
    "C5": 523, "Cs5": 554, "D5": 587, "Ds5": 622,
    "E5": 659, "F5": 698, "Fs5": 740, "G5": 784, "Gs5": 831,
    "A5": 880,
}


def play_melody(player, melody, label, sd_mount="/sd", lcd=None):
    """Play a melody using WAV samples if available, else synthio."""
    if sd_mount is not None:
        try:
            _play_wav(player, melody, label, sd_mount, lcd)
            return
        except OSError:
            pass
    _play_synth(player, melody, label, lcd)


def play_tetris(player, sd_mount="/sd", lcd=None):
    """Play Tetris using WAV samples if available, else synthio."""
    play_melody(player, TETRIS_THEME, "Tetris", sd_mount, lcd)


def _play_wav(player, melody, label, sd_mount, lcd=None):
    """Play melody using WAV note samples from SD card."""
    print("  Playing {} (WAV samples)...".format(label))
    if lcd:
        lcd.print(label, 0)

    voice = player.mixer.voice[0]
    voice.level = player.volume
    cur_file = None
    notes_shown = ""

    try:
        for name, ms in melody:
            voice.stop()
            if cur_file is not None:
                cur_file.close()
                cur_file = None

            if name is None:
                time.sleep(ms / 1000)
            else:
                if lcd:
                    notes_shown = _scroll_note(lcd, notes_shown, name)
                path = "{}/{}.wav".format(sd_mount, name)
                cur_file = open(path, "rb")
                wav = audiocore.WaveFile(cur_file)
                voice.play(wav)
                time.sleep(ms / 1000)
    except KeyboardInterrupt:
        pass

    voice.stop()
    if cur_file is not None:
        cur_file.close()
    print("  Done.")


def _scroll_note(lcd, notes_shown, name):
    """Append note name to scrolling LCD line 2."""
    if notes_shown:
        notes_shown += " " + name
    else:
        notes_shown = name
    # Show rightmost 16 chars
    if len(notes_shown) > 16:
        notes_shown = notes_shown[len(notes_shown) - 16:]
    lcd.print(notes_shown, 1)
    return notes_shown


def _play_synth(player, melody, label, lcd=None):
    """Fallback: play melody using synthio (no SD card needed)."""
    import synthio

    print("  Playing {} (synth fallback)...".format(label))
    if lcd:
        lcd.print(label, 0)

    synth = synthio.Synthesizer(sample_rate=player.mixer.sample_rate)
    envelope = synthio.Envelope(
        attack_time=0.01,
        decay_time=0.08,
        sustain_level=0.6,
        release_time=0.12,
    )

    voice = player.mixer.voice[0]
    voice.level = player.volume
    voice.play(synth)

    prev_note = None
    notes_shown = ""
    try:
        for name, ms in melody:
            if prev_note is not None:
                synth.release(prev_note)
                prev_note = None

            if name is None:
                time.sleep(ms / 1000)
            else:
                if lcd:
                    notes_shown = _scroll_note(lcd, notes_shown, name)
                note = synthio.Note(
                    frequency=FREQ[name],
                    envelope=envelope,
                )
                synth.press(note)
                prev_note = note
                time.sleep(ms / 1000)
    except KeyboardInterrupt:
        pass

    if prev_note is not None:
        synth.release(prev_note)
    time.sleep(0.15)
    voice.stop()
    print("  Done.")
