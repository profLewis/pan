"""
Digital hit sensor on GP2 (second Grove connector).
10K pull-down resistor between D0 and GND — reads LOW at rest, HIGH on hit.
"""

import machine
import time


class HitSensor:
    def __init__(self, pin=2, cooldown_ms=2000):
        self.pin = machine.Pin(pin, machine.Pin.IN)
        self.cooldown = cooldown_ms
        self.last_trigger = 0
        self.count = 0

    def check(self):
        """Return True once per hit, respecting cooldown."""
        if self.pin.value() == 1:
            now = time.ticks_ms()
            if time.ticks_diff(now, self.last_trigger) >= self.cooldown:
                self.last_trigger = now
                self.count += 1
                return True
        return False

    def reset(self):
        self.count = 0
        self.last_trigger = 0
