"""
Digital hit sensor on GP2 (second Grove connector).
10K pull-down resistor between D0 and GND — reads False at rest, True on hit.
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
        """Return True once per hit, respecting cooldown."""
        if self.dio.value:
            now = time.monotonic_ns() // 1_000_000
            if now - self.last_trigger >= self.cooldown:
                self.last_trigger = now
                self.count += 1
                return True
        return False

    def reset(self):
        self.count = 0
        self.last_trigger = 0

    def deinit(self):
        self.dio.deinit()
