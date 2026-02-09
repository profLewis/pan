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

# In the Mood (Glenn Miller) — main sax riff
# Swung eighths: long-short pairs use _E + _S
IN_THE_MOOD = [
    # Opening riff (rising pattern on A)
    ("A4", _E), ("A4", _S), ("C5", _S),
    ("E5", _E), ("E5", _S), ("E5", _E),
    ("G5", _E), ("E5", _E), ("C5", _E),
    ("A4", _Q),
    (None, _E),
    # Repeat riff
    ("A4", _E), ("A4", _S), ("C5", _S),
    ("E5", _E), ("E5", _S), ("E5", _E),
    ("G5", _E), ("E5", _E), ("C5", _E),
    ("A4", _Q),
    (None, _E),
    # Rising pattern on C
    ("C5", _E), ("C5", _S), ("E5", _S),
    ("G5", _E), ("G5", _S), ("G5", _E),
    ("A5", _E), ("G5", _E), ("E5", _E),
    ("C5", _Q),
    (None, _E),
    # Descending finish
    ("A5", _E), ("G5", _E), ("E5", _E), ("C5", _E),
    ("A4", _E), ("C5", _E), ("E5", _Q),
    (None, _E),
    ("E5", _Q), ("E5", _Q),
]

# Note frequencies for synthio fallback
FREQ = {
    "A4": 440, "As4": 466, "B4": 494,
    "C5": 523, "Cs5": 554, "D5": 587, "Ds5": 622,
    "E5": 659, "F5": 698, "Fs5": 740, "G5": 784, "Gs5": 831,
    "A5": 880,
}


def play_melody(player, melody, label, sd_mount="/sd"):
    """Play a melody using WAV samples if available, else synthio."""
    if sd_mount is not None:
        try:
            _play_wav(player, melody, label, sd_mount)
            return
        except OSError:
            pass
    _play_synth(player, melody, label)


def play_tetris(player, sd_mount="/sd"):
    """Play Tetris using WAV samples if available, else synthio."""
    play_melody(player, TETRIS_THEME, "Tetris", sd_mount)


def play_in_the_mood(player, sd_mount="/sd"):
    """Play In the Mood using WAV samples if available, else synthio."""
    play_melody(player, IN_THE_MOOD, "In the Mood", sd_mount)


def _play_wav(player, melody, label, sd_mount):
    """Play melody using WAV note samples from SD card."""
    print("  Playing {} (WAV samples)...".format(label))

    voice = player.mixer.voice[0]
    voice.level = player.volume
    cur_file = None

    try:
        for name, ms in melody:
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


def _play_synth(player, melody, label):
    """Fallback: play melody using synthio (no SD card needed)."""
    import synthio

    print("  Playing {} (synth fallback)...".format(label))

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
        for name, ms in melody:
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
