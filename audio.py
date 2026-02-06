"""
PWM audio playback for SEENGREAT Pico Expansion Mini Rev 2.1.
Outputs via GP18 (left) and GP19 (right) to the 3.5mm audio jack.

Streams WAV data from SD in chunks, decodes PCM samples to PWM duty
values, and plays them with microsecond-accurate timing.

44100Hz sources are downsampled 2x on the fly (to ~22050Hz effective)
so the MicroPython output loop can keep up without jitter.

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
_PWM_FREQ = const(50_000)  # PWM carrier freq (above audible, good resolution)
_MAX_RATE = const(22050)   # max sample rate the output loop can sustain

# Global volume: 0 (mute) to 10 (full)
_volume = 7


def set_volume(v):
    """Set playback volume (0-10)."""
    global _volume
    _volume = min(10, max(0, int(v)))
    return _volume


def get_volume():
    return _volume


def _calc_ds(sample_rate):
    """Return (downsample_factor, effective_period_us)."""
    ds = 1
    while sample_rate // (ds + 1) >= 8000 and sample_rate > _MAX_RATE * ds:
        ds += 1
    period_us = (1_000_000 * ds) // sample_rate
    return ds, period_us


def play_wav(path, duration_ms=0, quiet=False):
    """Play a WAV file through PWM.
    duration_ms: if >0, stop after this many ms (for partial note playback).
    quiet:       if True, suppress print output (used by melody player).
    """

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
        ds, period_us = _calc_ds(sample_rate)

        # cap playback length if duration_ms is set
        if duration_ms > 0:
            max_bytes = int(sample_rate * frame_bytes * duration_ms / 1000)
            data_bytes = min(data_bytes, max_bytes)

        if not quiet:
            ch_label = "stereo" if stereo else "mono"
            dur = data_bytes / (sample_rate * frame_bytes)
            ds_note = " ({}x downsample)".format(ds) if ds > 1 else ""
            print("  {}Hz  {}-bit  {}  ({:.1f}s)  vol={}{}".format(
                sample_rate, bits, ch_label, dur, _volume, ds_note))
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

                # output with downsampling
                _output(pwm_l, pwm_r, buf_l, buf_r, n, period_us, ds)

        except KeyboardInterrupt:
            print("\n  Stopped.")
        finally:
            pwm_l.duty_u16(0)
            pwm_r.duty_u16(0)
            pwm_l.deinit()
            pwm_r.deinit()

    if not quiet:
        print("  Playback finished.")


def play_notes(notes, sd_mount="/sd"):
    """Play a sequence of notes without PWM teardown between them.
    notes: list of (filename_or_None, duration_ms) tuples.
           None filename = rest/silence.
    Keeps PWM alive across all notes to avoid clicks/pops.
    """
    import time as _time

    # ---- set up PWM once ----
    pwm_l = machine.PWM(machine.Pin(_PIN_L))
    pwm_r = machine.PWM(machine.Pin(_PIN_R))
    pwm_l.freq(_PWM_FREQ)
    pwm_r.freq(_PWM_FREQ)
    pwm_l.duty_u16(_SILENCE)
    pwm_r.duty_u16(_SILENCE)

    raw = bytearray(_CHUNK)
    vol = _volume
    # pre-allocate decode buffer (mono 16-bit assumed for note files)
    max_frames = _CHUNK // 2
    buf = array("H", bytes(max_frames * 2))
    fade_len = 80  # samples to fade out at end of each note (post-downsample)

    try:
        for note, ms in notes:
            if note is None:
                # rest — hold silence
                pwm_l.duty_u16(_SILENCE)
                pwm_r.duty_u16(_SILENCE)
                _time.sleep_ms(ms)
                continue

            path = sd_mount + "/" + note
            try:
                f = open(path, "rb")
            except OSError:
                _time.sleep_ms(ms)
                continue

            # skip to data chunk
            riff = f.read(12)
            sample_rate = 44100
            frame_bytes = 2
            data_bytes = 0
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                tag = hdr[:4]
                sz = struct.unpack("<I", hdr[4:])[0]
                if tag == b"fmt ":
                    fmt = f.read(sz)
                    sample_rate = struct.unpack_from("<I", fmt, 4)[0]
                    frame_bytes = struct.unpack_from("<H", fmt, 12)[0]
                elif tag == b"data":
                    data_bytes = sz
                    break
                else:
                    f.read(sz)

            ds, period_us = _calc_ds(sample_rate)

            # how many bytes for the requested duration
            max_bytes = int(sample_rate * frame_bytes * ms / 1000)
            remaining = min(data_bytes, max_bytes)
            is_last_chunk = False

            while remaining > 0:
                to_read = min(_CHUNK, remaining)
                got = f.readinto(raw, to_read)
                if not got:
                    break
                remaining -= got
                n = got // frame_bytes

                _decode_mono_16(raw, buf, n, vol)

                # fade out at end of note to avoid click
                if remaining <= 0:
                    # figure out how many samples will actually be output
                    out_n = (n + ds - 1) // ds
                    fl = min(fade_len, out_n)
                    if fl > 0:
                        _fade_out_ds(buf, n, fl, ds)

                _output(pwm_l, pwm_r, buf, buf, n, period_us, ds)

            f.close()

    except KeyboardInterrupt:
        pass
    finally:
        pwm_l.duty_u16(0)
        pwm_r.duty_u16(0)
        pwm_l.deinit()
        pwm_r.deinit()


@micropython.native
def _fade_out_ds(buf, n, fade_len, ds):
    """Ramp the last fade_len output samples down to silence (accounting for ds step)."""
    # work backwards from end of buffer in steps of ds
    pos = n - ds  # last sample that will be output
    for i in range(fade_len):
        idx = pos - i * ds
        if idx < 0:
            break
        val = buf[idx]
        dev = val - 32768
        dev = (dev * i) // fade_len
        buf[idx] = 32768 + dev


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
        val = (val * vol) // 10
        buf[i] = val + 32768

@micropython.native
def _decode_mono_8(raw, buf, n, vol):
    for i in range(n):
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
def _output(pwm_l, pwm_r, buf_l, buf_r, n, period_us, step):
    """Push samples to PWM. step>1 skips samples (downsample)."""
    _ticks = time.ticks_us
    _add = time.ticks_add
    _diff = time.ticks_diff

    t = _ticks()
    i = 0
    while i < n:
        pwm_l.duty_u16(buf_l[i])
        pwm_r.duty_u16(buf_r[i])
        t = _add(t, period_us)
        while _diff(t, _ticks()) > 0:
            pass
        i += step
