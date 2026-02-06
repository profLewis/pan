"""
Melody player for SEENGREAT Pico Expansion Mini.
Plays Tetris theme using WAV note samples from SD card,
with synthio fallback if samples are unavailable.
"""

import time
import audiocore

# Tetris Theme A (Korobeiniki)
# (note_name, duration_ms)  — None = rest
_Q = 400    # quarter at ~150 BPM
_E = 200    # eighth
_DQ = 600   # dotted quarter

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


def play_tetris(player, sd_mount="/sd"):
    """Play Tetris using WAV samples if available, else synthio."""
    if sd_mount is not None:
        try:
            _play_wav(player, sd_mount)
            return
        except OSError:
            pass
    _play_synth(player)


def _play_wav(player, sd_mount):
    """Play Tetris theme using WAV note samples from SD card."""
    print("  Playing Tetris theme (WAV samples)...")

    voice = player.mixer.voice[0]
    voice.level = player.volume
    cur_file = None

    try:
        for name, ms in TETRIS_THEME:
            voice.stop()
            if cur_file is not None:
                cur_file.close()
                cur_file = None

            if name is None:
                time.sleep(ms / 1000)
            else:
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


def _play_synth(player):
    """Fallback: play Tetris theme using synthio (no SD card needed)."""
    import synthio

    print("  Playing Tetris theme (synth fallback)...")

    FREQ = {
        "A4": 440, "As4": 466, "B4": 494,
        "C5": 523, "Cs5": 554, "D5": 587, "Ds5": 622,
        "E5": 659, "F5": 698, "Fs5": 740, "G5": 784, "Gs5": 831,
        "A5": 880,
    }

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
    try:
        for name, ms in TETRIS_THEME:
            if prev_note is not None:
                synth.release(prev_note)
                prev_note = None

            if name is None:
                time.sleep(ms / 1000)
            else:
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
