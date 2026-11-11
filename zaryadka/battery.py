"""Чтение уровня заряда геймпадов Sony (DualShock 4 и DualSense).

Два способа получить данные:

* Linux: ядро (драйвер hid-playstation / hid-sony) само публикует батарею
  в /sys/class/power_supply — читаем оттуда, ничего ставить не нужно.
* Windows: читаем HID-отчёты геймпада через системные функции Windows
  (модуль winhid, без сторонних библиотек) и разбираем байт статуса.
* macOS (и Linux как запасной вариант): то же самое через библиотеку hidapi.

Раскладка отчётов взята из драйвера Linux hid-playstation.
"""

from __future__ import annotations

import glob
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

SONY_VID = 0x054C

DS4_PIDS = {
    0x05C4: "DualShock 4",
    0x09CC: "DualShock 4 (v2)",
    0x0BA0: "DualShock 4 (USB-адаптер)",
}
DUALSENSE_PIDS = {
    0x0CE6: "DualSense",
    0x0DF2: "DualSense Edge",
}

# Статусы
DISCHARGING = "discharging"
CHARGING = "charging"
FULL = "full"
UNKNOWN = "unknown"

STATUS_TEXT = {
    DISCHARGING: "от батареи",
    CHARGING: "заряжается",
    FULL: "заряжен полностью",
    UNKNOWN: "статус неизвестен",
}


@dataclass
class BatteryInfo:
    name: str
    level: Optional[int]  # 0..100, None если не удалось определить
    status: str
    connection: str  # "USB", "Bluetooth" или "?"
    key: str  # уникальный идентификатор устройства

    @property
    def status_text(self) -> str:
        return STATUS_TEXT.get(self.status, self.status)


# ---------------------------------------------------------------------------
# Разбор HID-отчётов (чистые функции, покрыты тестами)
# ---------------------------------------------------------------------------

DS4_USB_REPORT = 0x01
DS4_BT_REPORT = 0x11
DS4_USB_STATUS_OFFSET = 30  # байт статуса, считая с ID отчёта
DS4_BT_STATUS_OFFSET = 32

DS_USB_REPORT = 0x01
DS_BT_REPORT = 0x31
DS_USB_STATUS_OFFSET = 53
DS_BT_STATUS_OFFSET = 54


def decode_ds4_status(byte: int) -> tuple[Optional[int], str]:
    """Байт статуса DualShock 4 -> (процент, статус)."""
    level = byte & 0x0F
    cable = bool(byte & 0x10)
    if cable:
        if level < 10:
            return level * 10 + 5, CHARGING
        if level == 10:
            return 100, CHARGING
        if level == 11:
            return 100, FULL
        return None, UNKNOWN
    return min(level * 10 + 5, 100), DISCHARGING


def decode_dualsense_status(byte: int) -> tuple[Optional[int], str]:
    """Байт статуса DualSense -> (процент, статус)."""
    level = byte & 0x0F
    state = (byte & 0xF0) >> 4
    if state == 0x0:
        return min(level * 10 + 5, 100), DISCHARGING
    if state == 0x1:
        return min(level * 10 + 5, 100), CHARGING
    if state == 0x2:
        return 100, FULL
    return None, UNKNOWN


def parse_report(report: bytes, is_dualsense: bool, bluetooth: Optional[bool]):
    """Разбирает входной отчёт.

    Возвращает (процент, статус, "USB"/"Bluetooth") или None, если отчёт
    не содержит данных о батарее.

    bluetooth=None — тип подключения неизвестен; тогда короткий отчёт 0x01,
    который геймпад шлёт по Bluetooth до «пробуждения», отбрасывается по длине.
    """
    if not report:
        return None
    rid = report[0]
    if is_dualsense:
        if rid == DS_BT_REPORT and len(report) > DS_BT_STATUS_OFFSET:
            return (*decode_dualsense_status(report[DS_BT_STATUS_OFFSET]), "Bluetooth")
        if rid == DS_USB_REPORT and bluetooth is not True and len(report) >= 64:
            if _looks_padded(report):
                return None
            return (*decode_dualsense_status(report[DS_USB_STATUS_OFFSET]), "USB")
        return None
    if rid == DS4_BT_REPORT and len(report) > DS4_BT_STATUS_OFFSET:
        return (*decode_ds4_status(report[DS4_BT_STATUS_OFFSET]), "Bluetooth")
    if rid == DS4_USB_REPORT and bluetooth is not True and len(report) >= 64:
        if _looks_padded(report):
            return None
        return (*decode_ds4_status(report[DS4_USB_STATUS_OFFSET]), "USB")
    return None


def _looks_padded(report: bytes) -> bool:
    # Короткий BT-отчёт 0x01, дополненный нулями (так бывает в Windows):
    # после первых 10 байт одни нули.
    return not any(report[10:])


# ---------------------------------------------------------------------------
# Linux: sysfs
# ---------------------------------------------------------------------------

_SYSFS_PATTERNS = (
    "/sys/class/power_supply/ps-controller-battery-*",  # hid-playstation
    "/sys/class/power_supply/sony_controller_battery_*",  # старый hid-sony
)


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _sysfs_name(dev_dir: str) -> str:
    # .../power_supply/X/device -> HID-устройство, у него есть uevent с HID_NAME
    uevent = _read_text(os.path.join(dev_dir, "device", "uevent")) or ""
    hid_name = ""
    hid_id = ""
    for line in uevent.splitlines():
        if line.startswith("HID_NAME="):
            hid_name = line.split("=", 1)[1]
        elif line.startswith("HID_ID="):
            hid_id = line.split("=", 1)[1]
    try:
        pid = int(hid_id.split(":")[2], 16) if hid_id else None
    except (IndexError, ValueError):
        pid = None
    if pid in DS4_PIDS:
        return DS4_PIDS[pid]
    if pid in DUALSENSE_PIDS:
        return DUALSENSE_PIDS[pid]
    return hid_name or "Геймпад Sony"


def _sysfs_connection(dev_dir: str) -> str:
    uevent = _read_text(os.path.join(dev_dir, "device", "uevent")) or ""
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            bus = line.split("=", 1)[1].split(":")[0]
            if bus == "0003":
                return "USB"
            if bus == "0005":
                return "Bluetooth"
    return "?"


def read_sysfs() -> list[BatteryInfo]:
    result = []
    seen = set()
    for pattern in _SYSFS_PATTERNS:
        for dev_dir in sorted(glob.glob(pattern)):
            if dev_dir in seen:
                continue
            seen.add(dev_dir)
            cap = _read_text(os.path.join(dev_dir, "capacity"))
            st = (_read_text(os.path.join(dev_dir, "status")) or "").lower()
            status = {
                "discharging": DISCHARGING,
                "charging": CHARGING,
                "full": FULL,
            }.get(st, UNKNOWN)
            level = int(cap) if cap and cap.isdigit() else None
            result.append(
                BatteryInfo(
                    name=_sysfs_name(dev_dir),
                    level=level,
                    status=status,
                    connection=_sysfs_connection(dev_dir),
                    key=os.path.basename(dev_dir),
                )
            )
    return result


# ---------------------------------------------------------------------------
# hidapi (Windows / macOS / Linux без драйвера)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - зависит от окружения
    import hid  # type: ignore
except Exception:  # noqa: BLE001
    hid = None

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:  # pragma: no cover - только Windows
    from . import winhid

HID_UNAVAILABLE_MESSAGE = (
    "Не установлена библиотека hidapi. Выполните:  pip3 install hidapi"
)

_BT_GUID = "00001124-0000-1000-8000-00805f9b34fb"


def _is_bluetooth(info: dict) -> Optional[bool]:
    bus = info.get("bus_type")
    if bus is not None:
        # hidapi >= 0.14: 1 = USB, 2 = Bluetooth
        try:
            bus = int(bus)
        except (TypeError, ValueError):
            bus = None
        if bus == 1:
            return False
        if bus == 2:
            return True
    path = info.get("path") or b""
    if isinstance(path, bytes):
        path = path.decode("utf-8", "ignore")
    path = path.lower()
    if _BT_GUID in path or "bthenum" in path or "bluetooth" in path:
        return True
    if "usb" in path:
        return False
    return None


def _enumerate() -> list[dict]:
    if IS_WINDOWS:
        return winhid.enumerate_devices(SONY_VID)
    if hid is None:
        return []
    return hid.enumerate(SONY_VID, 0)


def _list_sony_devices() -> list[dict]:
    found = []
    seen_paths = set()
    for info in _enumerate():
        pid = info.get("product_id")
        if pid not in DS4_PIDS and pid not in DUALSENSE_PIDS:
            continue
        # У геймпада бывает несколько HID-интерфейсов — берём игровой.
        usage_page = info.get("usage_page")
        usage = info.get("usage")
        if usage_page not in (None, 0) and (usage_page, usage) != (0x01, 0x05):
            continue
        path = info.get("path")
        if path in seen_paths:
            continue
        seen_paths.add(path)
        found.append(info)
    return found


class _HidapiDevice:
    """Обёртка над hidapi с тем же интерфейсом, что у winhid.Device."""

    def __init__(self, path):
        if hasattr(hid, "device"):
            self.dev = hid.device()
            self.dev.open_path(path)
            self._legacy = True
        else:  # пакет "hid" вместо "hidapi"
            self.dev = hid.Device(path=path)
            self._legacy = False

    def get_feature_report(self, report_id: int, length: int):
        return self.dev.get_feature_report(report_id, length)

    def read(self, timeout_ms: int) -> bytes:
        if self._legacy:
            return bytes(self.dev.read(128, timeout_ms))
        return bytes(self.dev.read(128, timeout=timeout_ms) or b"")

    def close(self):
        self.dev.close()


def _open(info: dict):
    if IS_WINDOWS:
        return winhid.Device(info["path"])
    return _HidapiDevice(info["path"])


def _read_hid_device(info: dict, timeout: float = 1.5) -> BatteryInfo:
    pid = info["product_id"]
    is_ds = pid in DUALSENSE_PIDS
    name = DUALSENSE_PIDS.get(pid) or DS4_PIDS.get(pid, "Геймпад Sony")
    bt = _is_bluetooth(info)
    path = info.get("path")
    key = path.decode("utf-8", "ignore") if isinstance(path, bytes) else str(path)
    serial = info.get("serial_number")
    if serial:
        key = serial

    level, status = None, UNKNOWN
    connection = {True: "Bluetooth", False: "USB", None: "?"}[bt]

    dev = _open(info)
    try:
        # По Bluetooth геймпад шлёт урезанные отчёты, пока у него не запросят
        # feature-отчёт (0x02 для DS4, 0x05 для DualSense). На USB это безвредно.
        try:
            dev.get_feature_report(0x05 if is_ds else 0x02, 64 if is_ds else 37)
        except Exception:  # noqa: BLE001
            pass

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = dev.read(200)
            if not data:
                continue
            parsed = parse_report(bytes(data), is_ds, bt)
            if parsed is None:
                continue
            level, status, connection = parsed
            break
    finally:
        dev.close()

    return BatteryInfo(name=name, level=level, status=status, connection=connection, key=key)


def read_hid() -> list[BatteryInfo]:
    result = []
    for info in _list_sony_devices():
        try:
            result.append(_read_hid_device(info))
        except Exception as exc:  # noqa: BLE001
            pid = info.get("product_id")
            name = DUALSENSE_PIDS.get(pid) or DS4_PIDS.get(pid, "Геймпад Sony")
            result.append(
                BatteryInfo(
                    name=f"{name} (нет доступа: {exc})",
                    level=None,
                    status=UNKNOWN,
                    connection="?",
                    key=str(info.get("path")),
                )
            )
    return result


def read_all() -> list[BatteryInfo]:
    """Возвращает список подключённых геймпадов с уровнем заряда."""
    if sys.platform.startswith("linux"):
        found = read_sysfs()
        if found:
            return found
    return read_hid()


def backend_problem() -> Optional[str]:
    """Сообщение о проблеме окружения или None, если всё в порядке."""
    if IS_WINDOWS:
        return None
    if sys.platform.startswith("linux") and os.path.isdir("/sys/class/power_supply"):
        return None
    if hid is None:
        return HID_UNAVAILABLE_MESSAGE
    return None
