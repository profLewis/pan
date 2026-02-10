"""
Sensor driver for WAV-trigger input.

HitSensor — digital hit sensor on GP2 (Grove connector, 10K pull-down)

API:
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
