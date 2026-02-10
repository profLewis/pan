"""
Driver for Grove 16x2 LCD (JHD1802M2) over I2C.
Address 0x3E, HD44780-compatible commands via I2C.
"""

import time


class LCD:
    def __init__(self, i2c, address=0x3E):
        self._i2c = i2c
        self._addr = address
        self._buf = bytearray(2)
        while not i2c.try_lock():
            pass
        self._init_display()

    def _init_display(self):
        time.sleep(0.05)
        self._command(0x28)  # function set: 4-bit, 2 lines, 5x8
        self._command(0x0C)  # display on, cursor off
        self._command(0x01)  # clear
        time.sleep(0.002)
        self._command(0x06)  # entry mode: increment, no shift

    def _command(self, cmd):
        self._buf[0] = 0x80
        self._buf[1] = cmd
        self._i2c.writeto(self._addr, self._buf)
        time.sleep(0.001)

    def _data(self, val):
        self._buf[0] = 0x40
        self._buf[1] = val
        self._i2c.writeto(self._addr, self._buf)
        time.sleep(0.001)

    def clear(self):
        self._command(0x01)
        time.sleep(0.002)

    def set_cursor(self, col, row):
        offset = 0x40 if row else 0x00
        self._command(0x80 | (offset + col))

    def write(self, text):
        for c in text:
            self._data(ord(c))

    def print(self, text, row=0, clear_row=True):
        self.set_cursor(0, row)
        if clear_row:
            text = "{:<16}".format(text[:16])
        else:
            text = text[:16]
        self.write(text)

    def show(self, line1="", line2=""):
        self.print(line1, 0)
        self.print(line2, 1)

    def deinit(self):
        self.clear()
        self._i2c.unlock()
