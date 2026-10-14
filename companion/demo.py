"""Synthetic context for trying the UI. This is not game data or an AI response."""
import time


def snapshot():
    return {"kind": "forever-ai-snapshot", "schemaVersion": 1, "demo": True,
            "capturedAt": int(time.time()), "client": {"version": "UI-DEMO, not a real game build"},
            "player": {"level": 12, "zone": "示例营地（虚构）"},
            "quests": [
                {"id": 900001, "title": "示例：营地补给", "complete": True,
                 "objectives": [{"text": "收集补给 6/6", "finished": True}]},
                {"id": 900002, "title": "示例：森林采集", "complete": False,
                 "objectives": [{"text": "采集材料 2/8", "finished": False}]},
                {"id": 900003, "title": "示例：遗迹探索", "complete": False,
                 "objectives": [{"text": "寻找遗迹线索 0/1", "finished": False}]}]}


def example_picture():
    """A synthetic UI fixture, never described as a real map or AI generation."""
    import io
    from PIL import Image, ImageDraw
    from .core import ReplyImage
    picture = Image.new('RGB', (640, 360), '#172630')
    draw = ImageDraw.Draw(picture)
    draw.text((30, 22), 'OFFLINE EXAMPLE / FICTIONAL QUEST FLOW', fill='#ead5a4', font_size=20)
    for i, (title, detail) in enumerate((('1. Camp', 'Turn in'), ('2. Forest', 'Gather'), ('3. Ruins', 'Explore'))):
        x = 25 + i * 207
        draw.rounded_rectangle((x, 100, x + 178, 245), radius=14, fill='#233743', outline='#709aab', width=2)
        draw.text((x + 14, 126), title, fill='#e1e9ee', font_size=23)
        draw.text((x + 14, 185), detail, fill='#a8d5df', font_size=20)
        if i < 2:
            draw.line((x + 181, 173, x + 202, 173), fill='#ead5a4', width=3)
    draw.text((30, 302), 'UI preview only - not an actual game map', fill='#95adbb', font_size=19)
    data = io.BytesIO()
    picture.save(data, 'PNG')
    return ReplyImage(data.getvalue(), '离线示例 · 虚构任务流程，非游戏地图')
