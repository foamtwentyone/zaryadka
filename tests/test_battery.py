import unittest

from zaryadka.battery import (
    CHARGING, DISCHARGING, FULL, UNKNOWN,
    decode_ds4_status, decode_dualsense_status, parse_report,
)


def report(rid, size, offset, value):
    data = bytearray(size)
    data[0] = rid
    for i in range(1, size):
        data[i] = 0x80  # «живые» данные стиков, чтобы не выглядело как паддинг
    data[offset] = value
    return bytes(data)


class DecodeTests(unittest.TestCase):
    def test_ds4(self):
        self.assertEqual(decode_ds4_status(0x08), (85, DISCHARGING))
        self.assertEqual(decode_ds4_status(0x0A), (100, DISCHARGING))
        self.assertEqual(decode_ds4_status(0x00), (5, DISCHARGING))
        self.assertEqual(decode_ds4_status(0x13), (35, CHARGING))
        self.assertEqual(decode_ds4_status(0x1A), (100, CHARGING))
        self.assertEqual(decode_ds4_status(0x1B), (100, FULL))
        self.assertEqual(decode_ds4_status(0x1F), (None, UNKNOWN))

    def test_dualsense(self):
        self.assertEqual(decode_dualsense_status(0x04), (45, DISCHARGING))
        self.assertEqual(decode_dualsense_status(0x0A), (100, DISCHARGING))
        self.assertEqual(decode_dualsense_status(0x17), (75, CHARGING))
        self.assertEqual(decode_dualsense_status(0x20), (100, FULL))
        self.assertEqual(decode_dualsense_status(0xF0), (None, UNKNOWN))


class ParseTests(unittest.TestCase):
    def test_ds4_usb(self):
        self.assertEqual(parse_report(report(0x01, 64, 30, 0x06), False, False), (65, DISCHARGING, "USB"))

    def test_ds4_bt(self):
        self.assertEqual(parse_report(report(0x11, 78, 32, 0x1B), False, True), (100, FULL, "Bluetooth"))

    def test_ds4_bt_short_report_ignored(self):
        short = bytes([0x01, 0x80, 0x80, 0x80, 0x80, 0x08, 0, 0, 0, 0])
        self.assertIsNone(parse_report(short, False, None))
        padded = short + bytes(54)
        self.assertIsNone(parse_report(padded, False, None))
        self.assertIsNone(parse_report(report(0x01, 64, 30, 0x06), False, True))

    def test_dualsense_usb_and_bt(self):
        self.assertEqual(parse_report(report(0x01, 64, 53, 0x12), True, False), (25, CHARGING, "USB"))
        self.assertEqual(parse_report(report(0x31, 78, 54, 0x09), True, True), (95, DISCHARGING, "Bluetooth"))

    def test_empty(self):
        self.assertIsNone(parse_report(b"", False, None))


if __name__ == "__main__":
    unittest.main()
