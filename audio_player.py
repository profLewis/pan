"""
Polyphonic audio player for SEENGREAT Pico Expansion Mini Rev 2.1.
Uses CircuitPython audiomixer for real-time mixing of multiple WAV
files with per-voice volume control.

Audio output (PWM via PIO):
    Left  -> GP18  (buzzer + 3.5mm left)
    Right -> GP19  (3.5mm right)
"""

import board
import audiopwmio
import audiomixer
import audiocore

NUM_VOICES = 4


class AudioPlayer:
    def __init__(self, sample_rate=44100):
        self._out = audiopwmio.PWMAudioOut(
            board.GP18, right_channel=board.GP19
        )
        self._mixer = audiomixer.Mixer(
            voice_count=NUM_VOICES,
            sample_rate=sample_rate,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        self._out.play(self._mixer)
        self._vol = 1.5
        self._files = [None] * NUM_VOICES

    # ---- volume (0.0 – 2.0) ----

    @property
    def volume(self):
        return self._vol

    @volume.setter
    def volume(self, v):
        self._vol = max(0.0, min(2.0, float(v)))

    def volume_int(self):
        """Return volume as 0-10 integer."""
        return min(round(self._vol * 10), 20)

    def set_volume_int(self, v):
        """Set volume from 0-20 integer."""
        self.volume = int(v) / 10.0
        return self.volume_int()

    # ---- WAV playback ----

    @property
    def mixer(self):
        return self._mixer

    def play_wav(self, path, voice=None):
        """Play a WAV file. Auto-selects a free voice if voice is None.
        Returns the voice index used."""
        if voice is None:
            voice = self._free_voice()
        self._close_voice(voice)
        f = open(path, "rb")
        self._files[voice] = f
        wav = audiocore.WaveFile(f)
        self._mixer.voice[voice].level = self._vol
        self._mixer.voice[voice].play(wav)
        return voice

    def stop(self, voice=0):
        self._mixer.voice[voice].stop()
        self._close_voice(voice)

    def stop_all(self):
        for i in range(NUM_VOICES):
            self._mixer.voice[i].stop()
            self._close_voice(i)

    def is_playing(self, voice=0):
        return self._mixer.voice[voice].playing

    def any_playing(self):
        return any(self._mixer.voice[i].playing for i in range(NUM_VOICES))

    def wait(self):
        """Block until all voices finish."""
        import time
        while self.any_playing():
            time.sleep(0.01)

    # ---- internal ----

    def _free_voice(self):
        for i in range(NUM_VOICES):
            if not self._mixer.voice[i].playing:
                return i
        return 0  # steal oldest if all busy

    def _close_voice(self, i):
        if self._files[i]:
            try:
                self._files[i].close()
            except:
                pass
            self._files[i] = None

    def deinit(self):
        self.stop_all()
        self._out.stop()
        self._out.deinit()
