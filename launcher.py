"""Small native launcher for Desk Guardian; the monitoring app stays in the tray."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from src.config import load_settings
from src.single_instance import acquire, release

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / ("config.local.yaml" if (ROOT / "config.local.yaml").exists() else "config.yaml")
BG = "#0f1720"
SURFACE = "#18232f"
SURFACE_SOFT = "#202d3a"
TEXT = "#f4f7f9"
MUTED = "#a9b6c2"
GREEN = "#37b982"
GREEN_ACTIVE = "#2da672"
AMBER = "#e3a447"


def guardian_is_running() -> bool:
    handle = acquire()
    if handle is None:
        return True
    release(handle)
    return False


def guardian_command(enable_sleep: bool) -> list[str]:
    return [sys.executable, "-m", "src.main", "--enable-sleep" if enable_sleep else "--dry-run"]


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Desk Guardian")
        self.geometry("560x570")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.option_add("*Font", "{Segoe UI} 10")
        self.process: subprocess.Popen | None = None
        self._styles()
        self._build()
        self.after(100, self._center)

    def _styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Primary.TButton", background=GREEN, foreground="#07140f",
                        borderwidth=0, focusthickness=0, padding=(18, 14),
                        font=("Segoe UI Semibold", 11))
        style.map("Primary.TButton", background=[("active", GREEN_ACTIVE), ("disabled", "#355247")],
                  foreground=[("disabled", "#95a59f")])
        style.configure("Secondary.TButton", background=SURFACE_SOFT, foreground=TEXT,
                        bordercolor="#344555", borderwidth=1, focusthickness=0,
                        padding=(18, 14), font=("Segoe UI Semibold", 11))
        style.map("Secondary.TButton", background=[("active", "#2a3a48"), ("disabled", "#202a33")],
                  foreground=[("disabled", "#73808b")])

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{max(30, y - 25)}")

    def _build(self):
        body = tk.Frame(self, bg=BG, padx=42, pady=34)
        body.pack(fill="both", expand=True)

        brand = tk.Frame(body, bg=BG)
        brand.pack(fill="x")
        mark = tk.Canvas(brand, width=52, height=52, bg=BG, highlightthickness=0)
        mark.pack(side="left", padx=(0, 16))
        mark.create_oval(3, 3, 49, 49, fill=GREEN, outline="")
        mark.create_text(26, 26, text="DG", fill="#07140f", font=("Segoe UI Semibold", 13))
        title = tk.Frame(brand, bg=BG)
        title.pack(side="left", fill="x", expand=True)
        tk.Label(title, text="Desk Guardian", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 22)).pack(anchor="w")
        tk.Label(title, text="자리와 자세를 조용히 지켜보는 로컬 도우미", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 0))

        card = tk.Frame(body, bg=SURFACE, padx=22, pady=20,
                        highlightbackground="#2b3b49", highlightthickness=1)
        card.pack(fill="x", pady=(28, 22))
        settings = load_settings(DEFAULT_CONFIG)
        baseline_ready = (settings.db_path.parent / "baseline.json").exists()
        self.status_dot = tk.Label(card, text="●", bg=SURFACE,
                                   fg=GREEN if baseline_ready else AMBER, font=("Segoe UI", 12))
        self.status_dot.grid(row=0, column=0, sticky="nw", padx=(0, 9))
        self.status_title = tk.Label(card, text="실행 준비 완료" if baseline_ready else "자세 기준 설정 필요",
                                     bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 11))
        self.status_title.grid(row=0, column=1, sticky="w")
        self.status_detail = tk.Label(
            card,
            text="기준 자세 저장됨 · 데이터는 이 PC에만 저장" if baseline_ready
                 else "실행 후 트레이에서 자세 기준을 설정하세요",
            bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), justify="left")
        self.status_detail.grid(row=1, column=1, sticky="w", pady=(5, 0))

        tk.Label(body, text="실행 모드", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 10))
        self.safe_button = ttk.Button(body, text="안전 모드로 시작", style="Primary.TButton",
                                      command=lambda: self._start(False))
        self.safe_button.pack(fill="x")
        tk.Label(body, text="감지와 기록만 실행하며 컴퓨터를 절전하지 않습니다.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=3, pady=(7, 15))

        self.real_button = ttk.Button(body, text="자동 절전을 켜고 시작", style="Secondary.TButton",
                                      command=lambda: self._start(True))
        self.real_button.pack(fill="x")
        tk.Label(body, text="얼굴과 입력이 5분간 없으면 15초 전에 알리고 절전합니다.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=3, pady=(7, 0))

        footer = tk.Frame(body, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(24, 0))
        tk.Label(footer, text="실행 후 작업표시줄  ^  영역에서 관리할 수 있습니다.",
                 bg=BG, fg="#778794", font=("Segoe UI", 9)).pack(side="left")
        tk.Button(footer, text="닫기", command=self.destroy, bg=BG, fg=MUTED,
                  activebackground=BG, activeforeground=TEXT, relief="flat", bd=0,
                  cursor="hand2", font=("Segoe UI", 9)).pack(side="right")

    def _start(self, enable_sleep: bool):
        if guardian_is_running():
            self._show_running("Desk Guardian이 이미 실행 중입니다.")
            return
        if enable_sleep and not messagebox.askyesno(
                "자동 절전 켜기",
                "5분간 얼굴과 키보드·마우스 입력이 없으면 컴퓨터가 절전됩니다.\n\n계속할까요?",
                parent=self):
            return
        try:
            self.process = subprocess.Popen(guardian_command(enable_sleep), cwd=ROOT,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            messagebox.showerror("실행할 수 없습니다", f"Desk Guardian을 시작하지 못했습니다.\n{exc}", parent=self)
            return
        self.status_title.configure(text="시작하는 중…")
        self.status_detail.configure(text="카메라와 트레이 아이콘을 준비하고 있습니다.")
        self.safe_button.state(["disabled"])
        self.real_button.state(["disabled"])
        self.after(1200, lambda: self._verify(enable_sleep))

    def _verify(self, enable_sleep: bool):
        if self.process is not None and self.process.poll() is not None:
            self.status_dot.configure(fg="#e86666")
            self.status_title.configure(text="시작하지 못했습니다")
            self.status_detail.configure(text="이미 실행 중인지 확인하거나 로그를 확인하세요.")
            self.safe_button.state(["!disabled"])
            self.real_button.state(["!disabled"])
            return
        mode = "자동 절전 모드" if enable_sleep else "안전 모드"
        self._show_running(f"{mode}로 실행 중입니다.")
        self.after(1800, self.destroy)

    def _show_running(self, detail: str):
        self.status_dot.configure(fg=GREEN)
        self.status_title.configure(text="Desk Guardian 실행 중")
        self.status_detail.configure(text=detail + " 트레이 아이콘에서 관리하세요.")
        self.safe_button.state(["disabled"])
        self.real_button.state(["disabled"])


def main():
    Launcher().mainloop()


if __name__ == "__main__":
    main()
