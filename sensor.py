"""
Sensor driver for WAV-trigger input via CD74HC4067 16-channel multiplexer.

MuxSensor — scans mux channels for button presses.
    S0-S3 (channel select): GP2-GP5
    SIG   (read):           GP6
    EN:                     tied to GND (always enabled)

API:
    check()  -> list of channel IDs that just triggered (empty = no hits)
    count    — total hit count
    deinit() — cleanup
"""

import board
import digitalio
import time


class MuxSensor:
    def __init__(self, select_pins=None, sig_pin=None, channels=16,
                 cooldown_ms=200):
        if select_pins is None:
            select_pins = [board.GP2, board.GP3, board.GP4, board.GP5]
        if sig_pin is None:
            sig_pin = board.GP6

        # Set up select pins as outputs
        self._sel = []
        for pin in select_pins:
            dio = digitalio.DigitalInOut(pin)
            dio.direction = digitalio.Direction.OUTPUT
            dio.value = False
            self._sel.append(dio)

        # Set up SIG pin as input with pull-down
        self._sig = digitalio.DigitalInOut(sig_pin)
        self._sig.direction = digitalio.Direction.INPUT
        self._sig.pull = digitalio.Pull.DOWN

        self._channels = channels
        self.cooldown = cooldown_ms
        self._last = [0] * channels
        self.count = 0

    def _select(self, ch):
        """Set S0-S3 to select a mux channel."""
        for i, pin in enumerate(self._sel):
            pin.value = bool(ch & (1 << i))

    def check(self):
        """Scan all channels, return list of newly pressed channel IDs."""
        now = time.monotonic_ns() // 1_000_000
        triggered = []
        for ch in range(self._channels):
            self._select(ch)
            # Small settle time for mux (~1us needed, sleep(0) is fine)
            if self._sig.value and now - self._last[ch] >= self.cooldown:
                self._last[ch] = now
                self.count += 1
                triggered.append(ch)
        return triggered

    def reset(self):
        self.count = 0
        self._last = [0] * self._channels

    def deinit(self):
        for pin in self._sel:
            pin.deinit()
        self._sig.deinit()
