"""Render the SIRQ developer showcase as a lightweight animated GIF."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sirq.cli import build_runtime  # noqa: E402
from sirq.replay import read_jsonl  # noqa: E402

W, H = 900, 600
BG = (7, 15, 29)
PANEL = (15, 29, 49)
PANEL_2 = (19, 39, 64)
TEXT = (232, 241, 250)
MUTED = (145, 166, 191)
CYAN = (125, 211, 252)
GREEN = (74, 222, 128)
AMBER = (251, 191, 36)
RED = (251, 113, 133)
PURPLE = (196, 181, 253)


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


F_TITLE = font(46, True)
F_HERO = font(30, True)
F_HEAD = font(22, True)
F_BODY = font(18)
F_SMALL = font(15)
F_MONO = font(17)


def text(draw, xy, value, fill=TEXT, f=F_BODY, anchor=None):
    draw.text(xy, value, font=f, fill=fill, anchor=anchor)


def rounded(draw, box, fill=PANEL, outline=None, radius=18, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrapped(draw, value, x, y, max_width, fill=TEXT, f=F_BODY, spacing=6):
    words, lines, line = value.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=f)[2] <= max_width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for item in lines:
        text(draw, (x, y), item, fill, f)
        y += f.size + spacing
    return y


def base(title: str, subtitle: str = ""):
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 8), fill=CYAN)
    text(draw, (48, 42), title, f=F_HEAD)
    if subtitle:
        text(draw, (48, 76), subtitle, MUTED, F_SMALL)
    text(draw, (W - 48, 48), "SIRQ", CYAN, F_SMALL, anchor="ra")
    return image, draw


def slide_title():
    image, draw = base("Semantic Interrupt Request", "A semantic layer for software state")
    text(draw, (48, 170), "AI observes.", CYAN, F_TITLE)
    text(draw, (48, 230), "Software decides.", TEXT, F_TITLE)
    wrapped(draw, "SIRQ turns noisy telemetry into structured meaning without giving an AI control of the computer.", 52, 320, 690, MUTED, F_BODY)
    rounded(draw, (52, 440, 848, 520), PANEL, outline=(34, 60, 90))
    text(draw, (78, 470), "events tell computers what happened", MUTED, F_SMALL)
    text(draw, (522, 470), "SIRQ tells them what might matter", CYAN, F_SMALL)
    draw.line((430, 457, 485, 502), fill=PURPLE, width=3)
    return image


def slide_pipeline():
    image, draw = base("From raw state to safe action", "The core SIRQ boundary")
    labels = [("RAW STATE", "logs · metrics · agents", CYAN), ("SEMANTIC SENSOR", "what appears to be happening?", PURPLE), ("SIRQ EVENT", "structured meaning", AMBER), ("POLICY", "what is allowed?", GREEN)]
    y = 145
    for i, (head, body, color) in enumerate(labels):
        x = 62 + i * 210
        rounded(draw, (x, y, x + 178, y + 130), PANEL_2, outline=color)
        text(draw, (x + 89, y + 38), head, color, F_SMALL, anchor="ma")
        wrapped(draw, body, x + 18, y + 70, 142, TEXT, F_SMALL, 3)
        if i < 3:
            text(draw, (x + 190, y + 62), "→", MUTED, F_HERO, anchor="mm")
    rounded(draw, (62, 345, 838, 505), PANEL, outline=(34, 60, 90))
    text(draw, (92, 378), "The evaluator never receives:", RED, F_HEAD)
    for idx, item in enumerate(("shell access", "restart authority", "filesystem control", "arbitrary tools")):
        text(draw, (110 + (idx % 2) * 340, 435 + (idx // 2) * 38), f"×  {item}", MUTED, F_BODY)
    return image


def slide_decision(decision, headline, explanation, color):
    event = decision.event
    image, draw = base(headline, explanation)
    rounded(draw, (48, 135, 852, 520), PANEL, outline=color)
    text(draw, (82, 170), event.source, MUTED, F_SMALL)
    text(draw, (82, 208), event.kind, color, F_HERO)
    text(draw, (790, 216), f"P{event.priority}", color, F_HERO, anchor="ra")
    text(draw, (82, 282), "semantic confidence", MUTED, F_SMALL)
    text(draw, (82, 308), f"{event.confidence:.2f}", TEXT, F_HEAD)
    draw.rounded_rectangle((220, 315, 770, 334), radius=9, fill=(32, 54, 78))
    draw.rounded_rectangle((220, 315, 220 + int(550 * event.confidence), 334), radius=9, fill=color)
    text(draw, (82, 375), "human attention", MUTED, F_SMALL)
    text(draw, (82, 401), f"{event.human_attention:.2f}", TEXT, F_HEAD)
    draw.rounded_rectangle((220, 408, 770, 427), radius=9, fill=(32, 54, 78))
    draw.rounded_rectangle((220, 408, 220 + int(550 * event.human_attention), 427), radius=9, fill=RED)
    rounded(draw, (82, 462, 818, 500), PANEL_2, outline=color, radius=10)
    text(draw, (105, 481), f"deterministic decision:  {decision.handler}", color, F_BODY, anchor="lm")
    return image


def slide_stack():
    image, draw = base("Put it in the stack you already use", "SIRQ is a semantic layer, not a replacement for your tools")
    cards = [
        ("DOCKER", "container health", CYAN),
        ("CI/CD", "failed jobs", GREEN),
        ("WEBHOOKS", "tickets + alerts", AMBER),
        ("AI AGENTS", "blocked workers", PURPLE),
    ]
    for i, (head, body, color) in enumerate(cards):
        x = 52 + (i % 2) * 414
        y = 145 + (i // 2) * 145
        rounded(draw, (x, y, x + 365, y + 105), PANEL, outline=color)
        text(draw, (x + 24, y + 27), head, color, F_HEAD)
        text(draw, (x + 24, y + 68), body, TEXT, F_BODY)
        text(draw, (x + 330, y + 52), "→", MUTED, F_HERO, anchor="mm")
    rounded(draw, (52, 460, 848, 520), PANEL_2, outline=CYAN, radius=10)
    text(draw, (78, 490), "raw event", MUTED, F_SMALL, anchor="lm")
    text(draw, (285, 490), "SIRQ", CYAN, F_HEAD, anchor="lm")
    text(draw, (470, 490), "approved outcome", GREEN, F_SMALL, anchor="lm")
    text(draw, (792, 490), "→", MUTED, F_HEAD, anchor="rm")
    return image


def slide_replay():
    image, draw = base("Replay before authority", "Evaluate policies against historical state")
    text(draw, (52, 140), "sirq showcase.jsonl", CYAN, F_MONO)
    rows = [("github-actions / routine job", "IGNORE", GREEN), ("docker / payments-api", "RECORD", AMBER), ("auth webhook / credential anomaly", "NOTIFY", RED), ("coding agent / permission wall", "NOTIFY", RED)]
    for i, (name, action, color) in enumerate(rows):
        y = 195 + i * 58
        rounded(draw, (52, y, 848, y + 43), PANEL, outline=(34, 60, 90), radius=9)
        text(draw, (75, y + 22), name, TEXT, F_SMALL, anchor="lm")
        text(draw, (805, y + 22), action, color, F_SMALL, anchor="rm")
    wrapped(draw, "Tune thresholds, measure false positives, and compare policies before enabling reflexes.", 52, 455, 780, MUTED, F_BODY)
    return image


def transition(steps=4):
    """Use a brief dark wipe instead of crossfading text-heavy slides."""
    blank = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(blank)
    draw.rectangle((0, 0, W, 8), fill=CYAN)
    return [blank] * steps
def main():
    output = ROOT / "docs" / "assets" / "sirq-showcase.gif"
    output.parent.mkdir(parents=True, exist_ok=True)
    decisions = build_runtime().process_many(read_jsonl(ROOT / "examples" / "showcase.jsonl"))
    images = [
        slide_title(), slide_pipeline(), slide_stack(),
        slide_decision(decisions[0], "GitHub Actions noise stays quiet", "A scheduled job is busy, not broken.", GREEN),
        slide_decision(decisions[1], "Docker failure gets classified", "A retryable service problem becomes a recordable signal.", AMBER),
        slide_decision(decisions[2], "Webhook success can still be suspicious", "A 200 response does not prove everything is fine.", RED),
        slide_decision(decisions[3], "Coding agents wake humans", "Escalate permission boundaries, not every status update.", PURPLE),
        slide_replay(),
    ]
    frames = []
    for index, current in enumerate(images):
        frames.extend([current] * 12)
        if index + 1 < len(images):
            frames.extend(transition())
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=True)
    print(output)
    print(f"frames={len(frames)} size={output.stat().st_size}")


if __name__ == "__main__":
    main()
