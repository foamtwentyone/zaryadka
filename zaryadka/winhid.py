"""Доступ к HID-устройствам в Windows без сторонних библиотек (через ctypes).

Используются системные hid.dll, setupapi.dll и kernel32.dll — ничего
устанавливать и компилировать не нужно, работает на любой версии Python.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
HIDP_STATUS_SUCCESS = 0x00110000

BT_HID_GUID = "00001124-0000-1000-8000-00805f9b34fb"


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


_dlls = None


def _load():
    global _dlls
    if _dlls is not None:
        return _dlls
    hid = ctypes.WinDLL("hid", use_last_error=True)
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    hid.HidD_GetHidGuid.restype = None
    hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
    hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
    hid.HidP_GetCaps.restype = wintypes.LONG
    hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_GetFeature.restype = wintypes.BOOLEAN
    hid.HidD_GetSerialNumberString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_GetSerialNumberString.restype = wintypes.BOOLEAN

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
    ]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED),
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    ]
    kernel32.GetOverlappedResult.restype = wintypes.BOOL
    kernel32.CancelIo.argtypes = [wintypes.HANDLE]
    kernel32.CancelIo.restype = wintypes.BOOL
    kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    kernel32.ResetEvent.restype = wintypes.BOOL

    _dlls = (hid, setupapi, kernel32)
    return _dlls


INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _valid(handle) -> bool:
    return handle not in (None, 0, INVALID_HANDLE_VALUE)


def _device_paths() -> list[str]:
    hid, setupapi, _ = _load()
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if not _valid(info_set):
        return []
    paths = []
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                info_set, None, ctypes.byref(guid), index, ctypes.byref(iface)
            ):
                break
            index += 1
            required = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set, ctypes.byref(iface), None, 0, ctypes.byref(required), None
            )
            if required.value == 0:
                continue
            buf = ctypes.create_string_buffer(required.value)
            # cbSize структуры SP_DEVICE_INTERFACE_DETAIL_DATA_W: 8 на x64, 6 на x86
            cb = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            ctypes.c_uint32.from_buffer(buf).value = cb
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set, ctypes.byref(iface), buf, required, None, None
            ):
                continue
            paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info_set)
    return paths


def _open(path: str, access: int):
    _, _, kernel32 = _load()
    return kernel32.CreateFileW(
        path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
        OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None,
    )


def _caps(handle) -> HIDP_CAPS | None:
    hid, _, _ = _load()
    pp = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)):
        return None
    try:
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(pp, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
            return None
        return caps
    finally:
        hid.HidD_FreePreparsedData(pp)


def enumerate_devices(vendor_id: int) -> list[dict]:
    """Список HID-устройств производителя в формате, похожем на hidapi."""
    hid, _, kernel32 = _load()
    result = []
    for path in _device_paths():
        # Доступ 0 — только чтение атрибутов, открывается даже «занятое» устройство.
        handle = _open(path, 0)
        if not _valid(handle):
            continue
        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
            if not hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                continue
            if attrs.VendorID != vendor_id:
                continue
            caps = _caps(handle)
            serial_buf = ctypes.create_unicode_buffer(128)
            serial = None
            if hid.HidD_GetSerialNumberString(handle, serial_buf, ctypes.sizeof(serial_buf)):
                serial = serial_buf.value or None
            lower = path.lower()
            result.append(
                {
                    "path": path,
                    "vendor_id": attrs.VendorID,
                    "product_id": attrs.ProductID,
                    "usage_page": caps.UsagePage if caps else None,
                    "usage": caps.Usage if caps else None,
                    "serial_number": serial,
                    "bus_type": 2 if BT_HID_GUID in lower else None,
                }
            )
        finally:
            kernel32.CloseHandle(handle)
    return result


class Device:
    """Открытое HID-устройство с чтением по таймауту."""

    def __init__(self, path: str):
        self.hid, _, self.k32 = _load()
        self.handle = _open(path, GENERIC_READ | GENERIC_WRITE)
        if not _valid(self.handle):
            err = ctypes.get_last_error()
            raise OSError(err, f"не удалось открыть устройство (код {err}) — "
                               "возможно, его заняла другая программа")
        caps = _caps(self.handle)
        self.input_len = caps.InputReportByteLength if caps else 128
        self.feature_len = caps.FeatureReportByteLength if caps else 64
        self.event = self.k32.CreateEventW(None, True, False, None)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        size = max(length, self.feature_len)
        buf = ctypes.create_string_buffer(size)
        buf[0] = report_id
        if not self.hid.HidD_GetFeature(self.handle, buf, size):
            raise OSError(ctypes.get_last_error(), "feature report не прочитан")
        return buf.raw

    def read(self, timeout_ms: int) -> bytes:
        size = max(self.input_len, 1)
        buf = ctypes.create_string_buffer(size)
        ov = OVERLAPPED()
        ov.hEvent = self.event
        self.k32.ResetEvent(self.event)
        got = wintypes.DWORD(0)
        ok = self.k32.ReadFile(self.handle, buf, size, None, ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                raise OSError(err, f"ошибка чтения (код {err})")
            if self.k32.WaitForSingleObject(self.event, timeout_ms) != WAIT_OBJECT_0:
                self.k32.CancelIo(self.handle)
                # дождаться отмены, чтобы буфер не освободился раньше времени
                self.k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(got), True)
                return b""
        if not self.k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(got), True):
            return b""
        return buf.raw[: got.value]

    def close(self):
        if _valid(self.handle):
            self.k32.CloseHandle(self.handle)
            self.handle = None
        if self.event:
            self.k32.CloseHandle(self.event)
            self.event = None
