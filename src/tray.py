"""System tray controls send small commands to the single worker thread."""
from __future__ import annotations

from PIL import Image, ImageDraw
import pystray


def icon_image(color: str) -> Image.Image:
    colors = {"green": "#36b37e", "yellow": "#f4b942", "red": "#e85d5d"}
    image = Image.new("RGBA", (64, 64), "#192330")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 59, 59), radius=17, fill="#192330")
    draw.ellipse((15, 15, 48, 48), fill=colors[color])
    return image


class Tray:
    def __init__(self, commands):
        self.commands = commands
        self.colors = {name: icon_image(name) for name in ("green", "yellow", "red")}
        def dispatch(name):
            return lambda _icon, _item: self.commands.put(name)
        self.icon = pystray.Icon("desk_guardian", self.colors["yellow"], "Desk Guardian",
                                menu=pystray.Menu(
                                    pystray.MenuItem("30분 일시정지", dispatch("pause")),
                                    pystray.MenuItem("다시 시작", dispatch("resume")),
                                    pystray.MenuItem("자세 기준 설정", dispatch("calibrate")),
                                    pystray.MenuItem("대시보드 열기", dispatch("dashboard")),
                                    pystray.MenuItem("종료", dispatch("exit"))))
        self.color = "yellow"
        self.note = ""

    def set_color(self, color: str, note: str = ""):
        if color != self.color:
            self.icon.icon = self.colors[color]
            self.color = color
        if note != self.note:
            self.icon.title = "Desk Guardian · " + note if note else "Desk Guardian"
            self.note = note

    def run(self):
        self.icon.run()

    def stop(self):
        self.icon.stop()
