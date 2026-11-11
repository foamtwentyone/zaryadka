"""Окно и консольный режим Zaryadka."""

from __future__ import annotations

import argparse
import queue
import sys
import threading

from . import __version__
from .battery import CHARGING, FULL, BatteryInfo, backend_problem, read_all

REFRESH_MS = 5000
LOW_LEVEL = 20

BG = "#16181d"
CARD = "#22252d"
TEXT = "#f2f3f5"
MUTED = "#9aa0ab"
TRACK = "#3a3f4a"
GREEN = "#3ecf6e"
YELLOW = "#f2c94c"
RED = "#ef5350"
BLUE = "#4aa3ff"


def level_color(info: BatteryInfo) -> str:
    if info.status in (CHARGING, FULL):
        return BLUE
    if info.level is None:
        return MUTED
    if info.level <= LOW_LEVEL:
        return RED
    if info.level <= 50:
        return YELLOW
    return GREEN


def format_line(info: BatteryInfo) -> str:
    level = "—" if info.level is None else f"{info.level}%"
    return f"{info.name} [{info.connection}]: {level}, {info.status_text}"


def text_bar(level: int | None, width: int = 20) -> str:
    if level is None:
        return "[" + "?" * width + "]"
    filled = round(width * level / 100)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


# ---------------------------------------------------------------------------
# Консоль
# ---------------------------------------------------------------------------

def run_cli(watch: bool) -> int:
    import time

    problem = backend_problem()
    if problem:
        print(problem, file=sys.stderr)
        return 2
    while True:
        items = read_all()
        if not items:
            print("Геймпад не найден. Подключите DualShock по USB или Bluetooth.")
        for info in items:
            print(f"{text_bar(info.level)} {format_line(info)}")
        if not watch:
            return 0
        print("-" * 40)
        try:
            time.sleep(REFRESH_MS / 1000)
        except KeyboardInterrupt:
            return 0


# ---------------------------------------------------------------------------
# Окно
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.results: "queue.Queue[list[BatteryInfo] | Exception]" = queue.Queue()
        self.busy = False

        root.title("Заряд геймпада")
        root.configure(bg=BG)
        root.minsize(340, 160)
        root.resizable(False, False)

        self.on_top = tk.BooleanVar(value=False)

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            header, text="🎮 Заряд геймпада", bg=BG, fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")
        tk.Checkbutton(
            header, text="поверх окон", variable=self.on_top, command=self._toggle_top,
            bg=BG, fg=MUTED, selectcolor=CARD, activebackground=BG,
            activeforeground=TEXT, highlightthickness=0, bd=0,
        ).pack(side="right")

        self.cards = tk.Frame(root, bg=BG)
        self.cards.pack(fill="both", expand=True, padx=16)

        self.footer = tk.Label(
            root, text="Поиск геймпадов…", bg=BG, fg=MUTED, font=("Segoe UI", 9)
        )
        self.footer.pack(fill="x", padx=16, pady=(6, 12))

        problem = backend_problem()
        if problem:
            self._message(problem)
            return

        self.refresh()
        self.root.after(100, self._poll_results)

    def _toggle_top(self):
        self.root.attributes("-topmost", self.on_top.get())

    # Чтение HID может занимать до пары секунд — делаем его в фоне,
    # чтобы окно не подвисало.
    def refresh(self):
        if not self.busy:
            self.busy = True
            threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(REFRESH_MS, self.refresh)

    def _worker(self):
        try:
            self.results.put(read_all())
        except Exception as exc:  # noqa: BLE001
            self.results.put(exc)

    def _poll_results(self):
        try:
            while True:
                item = self.results.get_nowait()
                self.busy = False
                if isinstance(item, Exception):
                    self._message(f"Ошибка: {item}")
                else:
                    self._render(item)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_results)

    def _clear(self):
        for child in self.cards.winfo_children():
            child.destroy()

    def _message(self, text: str):
        self._clear()
        self.tk.Label(
            self.cards, text=text, bg=CARD, fg=TEXT, wraplength=300,
            justify="left", padx=14, pady=14, font=("Segoe UI", 10),
        ).pack(fill="x", pady=4)
        self.footer.config(text=f"v{__version__}")
        self.root.title("Заряд геймпада")

    def _render(self, items: list[BatteryInfo]):
        import time

        if not items:
            self._message(
                "Геймпад не найден.\nПодключите DualShock кабелем или по Bluetooth — "
                "окно обновится само."
            )
            self.footer.config(text=f"Обновлено {time.strftime('%H:%M:%S')} · v{__version__}")
            return

        self._clear()
        for info in items:
            self._card(info)
        self.footer.config(
            text=f"Обновлено {time.strftime('%H:%M:%S')} · каждые {REFRESH_MS // 1000} с · v{__version__}"
        )

        first = items[0]
        if first.level is not None:
            self.root.title(f"{first.level}% — заряд геймпада")

    def _card(self, info: BatteryInfo):
        tk = self.tk
        color = level_color(info)
        card = tk.Frame(self.cards, bg=CARD, padx=14, pady=12)
        card.pack(fill="x", pady=4)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        tk.Label(
            top, text=info.name, bg=CARD, fg=TEXT, font=("Segoe UI", 11, "bold")
        ).pack(side="left")
        tk.Label(
            top, text=info.connection, bg=CARD, fg=MUTED, font=("Segoe UI", 9)
        ).pack(side="right")

        mid = tk.Frame(card, bg=CARD)
        mid.pack(fill="x", pady=(6, 4))
        level_text = "—" if info.level is None else f"{info.level}%"
        tk.Label(
            mid, text=level_text, bg=CARD, fg=color, font=("Segoe UI", 26, "bold")
        ).pack(side="left")
        icon = {"charging": "⚡ ", "full": "✓ "}.get(info.status, "")
        tk.Label(
            mid, text=icon + info.status_text, bg=CARD, fg=MUTED, font=("Segoe UI", 10)
        ).pack(side="left", padx=(10, 0), anchor="s", pady=(0, 8))

        width, height = 300, 10
        bar = tk.Canvas(card, width=width, height=height, bg=CARD, highlightthickness=0)
        bar.pack(fill="x")
        bar.create_rectangle(0, 0, width, height, fill=TRACK, outline="")
        if info.level is not None:
            bar.create_rectangle(
                0, 0, max(2, width * info.level // 100), height, fill=color, outline=""
            )

        if info.level is not None and info.level <= LOW_LEVEL and info.status not in (CHARGING, FULL):
            tk.Label(
                card, text="Пора поставить на зарядку", bg=CARD, fg=RED,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(6, 0))


def run_gui() -> int:
    try:
        import tkinter as tk
    except ImportError:
        print("tkinter недоступен — запускаю консольный режим.", file=sys.stderr)
        return run_cli(watch=True)
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="zaryadka", description="Показывает уровень заряда DualShock 4 / DualSense."
    )
    parser.add_argument("--cli", action="store_true", help="вывести заряд в консоль и выйти")
    parser.add_argument("--watch", action="store_true", help="консольный режим с обновлением")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.cli or args.watch:
        return run_cli(watch=args.watch)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
