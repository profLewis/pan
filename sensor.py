"""
Sensor drivers for WAV-trigger input.

HitSensor     — digital hit sensor on GP2 (Grove connector, 10K pull-down)
MPR121Sensor  — 12-channel capacitive touch via I2C (SDA=GP5, SCL=GP4)

Both expose the same API:
    check()  -> list of channel IDs that just triggered (empty = no hits)
    count    — total hit count
    deinit() — cleanup
"""

import board
import digitalio
import time


class HitSensor:
    def __init__(self, pin=board.GP2, cooldown_ms=2000):
        self.dio = digitalio.DigitalInOut(pin)
        self.dio.direction = digitalio.Direction.INPUT
        self.cooldown = cooldown_ms
        self.last_trigger = 0
        self.count = 0

    def check(self):
        """Return [0] on hit (with cooldown), [] otherwise."""
        if self.dio.value:
            now = time.monotonic_ns() // 1_000_000
            if now - self.last_trigger >= self.cooldown:
                self.last_trigger = now
                self.count += 1
                return [0]
        return []

    def reset(self):
        self.count = 0
        self.last_trigger = 0

    def deinit(self):
        self.dio.deinit()


class MPR121Sensor:
    def __init__(self, sda=board.GP5, scl=board.GP4, address=0x5A,
                 cooldown_ms=200):
        import busio
        import adafruit_mpr121

        self._i2c = busio.I2C(scl, sda)
        self._mpr = adafruit_mpr121.MPR121(self._i2c, address=address)
        self.cooldown = cooldown_ms
        self._prev_touched = 0
        self._last_trigger = [0] * 12
        self.count = 0

    def check(self):
        """Return list of channel numbers with new touches (rising edges)."""
        cur = self._mpr.touched()
        now = time.monotonic_ns() // 1_000_000
        triggered = []
        for ch in range(12):
            bit = 1 << ch
            # Rising edge: not previously touched, now touched
            if (cur & bit) and not (self._prev_touched & bit):
                if now - self._last_trigger[ch] >= self.cooldown:
                    self._last_trigger[ch] = now
                    self.count += 1
                    triggered.append(ch)
        self._prev_touched = cur
        return triggered

    def reset(self):
        self.count = 0
        self._prev_touched = 0
        self._last_trigger = [0] * 12

    def deinit(self):
        self._i2c.deinit()
