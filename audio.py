"""
PWM audio playback for SEENGREAT Pico Expansion Mini Rev 2.1.
Outputs via GP18 (left) and GP19 (right) to the 3.5mm audio jack.

Streams WAV data from SD in chunks, decodes PCM samples to PWM duty
values, and plays them with microsecond-accurate timing.

Supports 8-bit and 16-bit PCM, mono and stereo, with volume control.
Volume is an integer 0-10 (0 = mute, 10 = full).
"""

import machine
import time
import struct
from array import array

_PIN_L = const(18)
_PIN_R = const(19)
_CHUNK = const(2048)       # bytes per SD read
_SILENCE = const(32768)    # midpoint = silence for unsigned 16-bit PWM
_PWM_FREQ = const(100_000) # PWM carrier frequency (well above audible)

# Global volume: 0 (mute) to 10 (full)
_volume = 7


def set_volume(v):
    """Set playback volume (0-10)."""
    global _volume
    _volume = min(10, max(0, int(v)))
    return _volume


def get_volume():
    return _volume


def play_wav(path):
    """Play a WAV file through PWM. Press Ctrl+C to stop."""

    with open(path, "rb") as f:
        # ---- parse RIFF / WAV header ----
        riff = f.read(12)
        if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:] != b"WAVE":
            print("  Not a valid WAV file.")
            return

        channels = 1
        sample_rate = 44100
        bits = 16

        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                print("  WAV: data chunk not found.")
                return
            tag = hdr[:4]
            sz = struct.unpack("<I", hdr[4:])[0]
            if tag == b"fmt ":
                fmt = f.read(sz)
                afmt = struct.unpack_from("<H", fmt, 0)[0]
                if afmt != 1:
                    print("  Only PCM WAV is supported (got format {}).".format(afmt))
                    return
                channels = struct.unpack_from("<H", fmt, 2)[0]
                sample_rate = struct.unpack_from("<I", fmt, 4)[0]
                bits = struct.unpack_from("<H", fmt, 14)[0]
            elif tag == b"data":
                data_bytes = sz
                break
            else:
                f.read(sz)

        frame_bytes = (bits // 8) * channels
        stereo = channels >= 2
        ch_label = "stereo" if stereo else "mono"
        dur = data_bytes / (sample_rate * frame_bytes)
        print("  {}Hz  {}-bit  {}  ({:.1f}s)  vol={}".format(
            sample_rate, bits, ch_label, dur, _volume))
        print("  Ctrl+C to stop")

        # ---- set up PWM on both audio pins ----
        pwm_l = machine.PWM(machine.Pin(_PIN_L))
        pwm_r = machine.PWM(machine.Pin(_PIN_R))
        pwm_l.freq(_PWM_FREQ)
        pwm_r.freq(_PWM_FREQ)
        pwm_l.duty_u16(_SILENCE)
        pwm_r.duty_u16(_SILENCE)

        # ---- pre-allocate buffers ----
        raw = bytearray(_CHUNK)
        max_frames = _CHUNK // frame_bytes
        buf_l = array("H", bytes(max_frames * 2))
        buf_r = array("H", bytes(max_frames * 2)) if stereo else buf_l

        period_us = 1_000_000 // sample_rate
        remaining = data_bytes
        vol = _volume

        try:
            while remaining > 0:
                to_read = min(_CHUNK, remaining)
                got = f.readinto(raw, to_read)
                if not got:
                    break
                remaining -= got
                n = got // frame_bytes

                # decode raw PCM -> unsigned 16-bit duty values (with volume)
                if stereo:
                    if bits == 16:
                        _decode_stereo_16(raw, buf_l, buf_r, n, vol)
                    else:
                        _decode_stereo_8(raw, buf_l, buf_r, n, vol)
                else:
                    if bits == 16:
                        _decode_mono_16(raw, buf_l, n, vol)
                    else:
                        _decode_mono_8(raw, buf_l, n, vol)

                # output samples with precise timing
                _output(pwm_l, pwm_r, buf_l, buf_r, n, period_us)

        except KeyboardInterrupt:
            print("\n  Stopped.")
        finally:
            pwm_l.duty_u16(0)
            pwm_r.duty_u16(0)
            pwm_l.deinit()
            pwm_r.deinit()

    print("  Playback finished.")


# ---- decode functions (native-compiled for speed) ----
# Volume is applied here: scale the signed deviation from centre by vol/10,
# then shift back to unsigned 16-bit range for duty_u16().

@micropython.native
def _decode_mono_16(raw, buf, n, vol):
    for i in range(n):
        off = i << 1
        val = raw[off] | (raw[off + 1] << 8)
        if val >= 32768:
            val -= 65536
        # val is signed (-32768..32767), scale by volume
        val = (val * vol) // 10
        buf[i] = val + 32768

@micropython.native
def _decode_mono_8(raw, buf, n, vol):
    for i in range(n):
        # 8-bit unsigned: 0-255, centre is 128
        val = raw[i] - 128
        val = (val * vol) // 10
        buf[i] = (val + 128) << 8

@micropython.native
def _decode_stereo_16(raw, buf_l, buf_r, n, vol):
    for i in range(n):
        off = i << 2
        vl = raw[off] | (raw[off + 1] << 8)
        vr = raw[off + 2] | (raw[off + 3] << 8)
        if vl >= 32768:
            vl -= 65536
        if vr >= 32768:
            vr -= 65536
        vl = (vl * vol) // 10
        vr = (vr * vol) // 10
        buf_l[i] = vl + 32768
        buf_r[i] = vr + 32768

@micropython.native
def _decode_stereo_8(raw, buf_l, buf_r, n, vol):
    for i in range(n):
        off = i << 1
        vl = raw[off] - 128
        vr = raw[off + 1] - 128
        vl = (vl * vol) // 10
        vr = (vr * vol) // 10
        buf_l[i] = (vl + 128) << 8
        buf_r[i] = (vr + 128) << 8


# ---- sample output (native-compiled tight loop) ----

@micropython.native
def _output(pwm_l, pwm_r, buf_l, buf_r, n, period_us):
    """Push n samples to PWM with microsecond-accurate spacing."""
    _ticks = time.ticks_us
    _add = time.ticks_add
    _diff = time.ticks_diff

    t = _ticks()
    for i in range(n):
        pwm_l.duty_u16(buf_l[i])
        pwm_r.duty_u16(buf_r[i])
        t = _add(t, period_us)
        while _diff(t, _ticks()) > 0:
            pass
