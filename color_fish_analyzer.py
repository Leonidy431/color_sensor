import smbus
import time
import struct
import threading
import json
from collections import deque

# AS7262 registers from datasheet
AS7262_ADDR = 0x49
INTEGRATION_TIME = 0x40  # 0-256 ms
GAIN = 0x41  # 1x-128x
STATUS_REG = 0x00
DATA_REG = 0x04  # violet to red: 450,500,550,570,600,650 nm

bus = smbus.SMBus(1)  # BlueOS RPi I2C bus 1

class ColorFishAnalyzer:
    def __init__(self):
        self.data_queue = deque(maxlen=10)
        self.running = False
        self.channels = ['violet', 'blue', 'green', 'yellow', 'orange', 'red']  # Approx wavelengths [web:7]

    def write_reg(self, reg, val):
        bus.write_byte_data(AS7262_ADDR, reg, val)

    def read_data(self):
        # Set integration 50ms, gain 3x [web:3]
        self.write_reg(INTEGRATION_TIME, 50)
        self.write_reg(GAIN, 3)
        self.write_reg(0x02, 0x01)  # Start measurement

        while True:
            status = bus.read_byte_data(AS7262_ADDR, STATUS_REG)
            if status & 0x01:  # Data ready
                break
            time.sleep(0.01)

        raw = bus.read_i2c_block_data(AS7262_ADDR, DATA_REG, 12)  # 16-bit per channel x6
        spectrum = []
        for i in range(6):
            val = struct.unpack('<HH', bytes(raw[2*i:2*i+2]))[0] / 65535.0  # Normalize 0-1
            spectrum.append(val)
        return dict(zip(self.channels, spectrum))

    def analyze_color(self, spec):
        # Pseudo-RGB from spectrum (approx mapping) [web:5]
        r = spec['red'] + 0.5 * spec['orange']
        g = spec['green'] + 0.5 * spec['yellow']
        b = spec['blue'] + spec['violet']
        total = r + g + b
        if total > 0:
            r, g, b = r/total, g/total, b/total

        # HSV-like for fish color: H from dominant, S saturation, V=1 [web:10]
        maxc = max(r, g, b)
        h = 0
        if maxc == r: h = (0.5 * (g - b) / maxc + 0) % 1 * 360
        elif maxc == g: h = (0.5 * (b - r) / maxc + 2) % 1 * 360
        else: h = (0.5 * (r - g) / maxc + 4) % 1 * 360
        s = 1 - 3 * min(r, g, b) / (r + g + b + 1e-6)

        # Fish color classification (customize thresholds for species)
        if 0 <= h <= 30 or 330 <= h <= 360: color = "Красная/Оранжевая"
        elif 30 < h <= 90: color = "Желтая"
        elif 90 < h <= 150: color = "Зеленая"
        elif 150 < h <= 240: color = "Голубая"
        elif 240 < h <= 300: color = "Синяя/Фиолетовая"
        else: color = "Неопределенный"
        freshness = "Свежая" if s > 0.6 else "Подозрительная"  # High saturation = vibrant [web:14]
        return {'spectrum': spec, 'rgb_approx': [r,g,b], 'hsv': [h,s,1], 'color': color, 'freshness': freshness}

    def sensor_loop(self):
        while self.running:
            data = self.read_data()
            analysis = self.analyze_color(data)
            self.data_queue.append(analysis)
            time.sleep(1)  # 1 Hz

    def start(self):
        self.running = True
        threading.Thread(target=self.sensor_loop, daemon=True).start()

    def get_latest(self):
        return list(self.data_queue)[-1] if self.data_queue else None

# BlueOS integration: expose via HTTP or MAVLink
if __name__ == "__main__":
    analyzer = ColorFishAnalyzer()
    analyzer.start()
    try:
        while True:
            latest = analyzer.get_latest()
            if latest:
                print(json.dumps(latest))
            time.sleep(5)
    except KeyboardInterrupt:
        analyzer.running = False
