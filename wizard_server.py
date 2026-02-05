#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from wizard_config import STEPS

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "wizard_state.json"


CSS = """
:root {
  --bg: #0f1020;
  --bg-2: #1b1c32;
  --accent: #f7b267;
  --accent-2: #f79d65;
  --ink: #f6f4f1;
  --muted: #b6b2a9;
  --card: rgba(255, 255, 255, 0.06);
  --card-strong: rgba(255, 255, 255, 0.12);
  --ok: #7bd389;
  --warn: #f4d35e;
  --err: #ee6c4d;
  --shadow: rgba(4, 6, 18, 0.35);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Georgia", "Times New Roman", serif;
  color: var(--ink);
  background: radial-gradient(1200px 900px at 10% 10%, #2b2e4a 0%, var(--bg) 45%, #0a0b16 100%);
  min-height: 100vh;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  background:
    linear-gradient(transparent 0 95%, rgba(255,255,255,0.02) 95% 100%),
    linear-gradient(90deg, transparent 0 95%, rgba(255,255,255,0.02) 95% 100%);
  background-size: 40px 40px;
  pointer-events: none;
  opacity: 0.35;
}

main {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 80px;
}

header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 24px;
}

h1 {
  font-weight: 700;
  font-size: 34px;
  letter-spacing: 0.5px;
  margin: 0;
}

.subtitle {
  color: var(--muted);
  font-size: 16px;
}

.grid {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(320px, 2fr);
  gap: 24px;
}

.card {
  background: var(--card);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
  padding: 20px 22px;
  box-shadow: 0 20px 50px var(--shadow);
  backdrop-filter: blur(6px);
  animation: fadeIn 0.6s ease both;
}

.card strong {
  font-weight: 700;
  letter-spacing: 0.4px;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-item {
  padding: 12px 14px;
  background: var(--card-strong);
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  animation: slideUp 0.5s ease both;
}

.status-title {
  font-size: 15px;
}

.badge {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-family: "Courier New", monospace;
}

.badge.pending { background: rgba(246,244,241,0.12); color: var(--muted); }
.badge.running { background: rgba(244,211,94,0.18); color: var(--warn); }
.badge.success { background: rgba(123,211,137,0.2); color: var(--ok); }
.badge.failed { background: rgba(238,108,77,0.2); color: var(--err); }

form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

label {
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
}

input[type="text"],
input[type="url"],
input[type="number"] {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.2);
  background: rgba(15,16,32,0.75);
  color: var(--ink);
  font-size: 15px;
}

input[type="checkbox"] {
  width: 18px;
  height: 18px;
}

.help {
  font-size: 13px;
  color: var(--muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

button, .btn-link {
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  border: none;
  color: #2a1f12;
  font-weight: 700;
  padding: 10px 16px;
  border-radius: 12px;
  cursor: pointer;
  text-decoration: none;
  text-align: center;
}

.btn-link.secondary {
  background: rgba(255,255,255,0.1);
  color: var(--ink);
}

pre {
  background: rgba(10, 10, 18, 0.7);
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.12);
  color: #dcd7cc;
  font-size: 12.5px;
  line-height: 1.6;
  max-height: 400px;
  overflow: auto;
}

@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
"""


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "current_step": 0,
        "values": {},
        "steps": {},
    }


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_FILE)


def status_label(state: dict, step_id: str) -> str:
    return state.get("steps", {}).get(step_id, {}).get("status", "pending")


def render_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>"""


def render_header(step, index, total) -> str:
    return f"""
<header>
  <h1>Мастер-панель запуска скриптов</h1>
  <div class=\"subtitle\">Шаг {index + 1} из {total} • {html.escape(step['title'])}</div>
</header>
"""


def render_status_list(state: dict, current_index: int) -> str:
    items = []
    for idx, step in enumerate(STEPS):
        status = status_label(state, step["id"])
        title = html.escape(step["title"])
        mark = "→" if idx == current_index else ""
        items.append(
            f"""
<div class=\"status-item\">
  <div class=\"status-title\">{mark} {title}</div>
  <div class=\"badge {status}\">{status}</div>
</div>
"""
        )
    return "<div class=\"status-list\">" + "".join(items) + "</div>"


def render_fields(state: dict, step: dict) -> str:
    values = state.get("values", {})
    parts = []
    for field in step["fields"]:
        key = field["key"]
        ftype = field.get("type", "text")
        label = html.escape(field["label"])
        help_text = html.escape(field.get("help", ""))
        placeholder = html.escape(field.get("placeholder", ""))
        required = "required" if field.get("required") else ""
        value = values.get(key, "")
        if ftype == "checkbox":
            checked = "checked" if value in ("y", "yes", "on", True) else ""
            input_html = (
                f"<input type=\"checkbox\" name=\"{key}\" {checked} />"
            )
        else:
            extra = ""
            if "step" in field:
                extra += f" step=\"{field['step']}\""
            if "min" in field:
                extra += f" min=\"{field['min']}\""
            input_html = (
                f"<input type=\"{ftype}\" name=\"{key}\" "
                f"value=\"{html.escape(str(value))}\" "
                f"placeholder=\"{placeholder}\" {required}{extra} />"
            )
        parts.append(
            f"""
<div class=\"field\">
  <label>{label}</label>
  {input_html}
  <div class=\"help\">{help_text}</div>
</div>
"""
        )
    return "".join(parts)


def render_output(state: dict, step_id: str) -> str:
    data = state.get("steps", {}).get(step_id)
    if not data:
        return "<div class=\"help\">Пока нет вывода.</div>"
    output = html.escape(data.get("output", ""))
    meta = html.escape(data.get("summary", ""))
    return f"""
<div class=\"help\">{meta}</div>
<pre>{output}</pre>
"""


def render_step_page(state: dict, step_index: int) -> str:
    step = STEPS[step_index]
    header = render_header(step, step_index, len(STEPS))
    status = render_status_list(state, step_index)
    fields_html = render_fields(state, step)
    output_html = render_output(state, step["id"])
    description = html.escape(step.get("description", ""))

    body = f"""
{header}
<div class=\"grid\">
  <section class=\"card\">
    <strong>Очередь шагов</strong>
    {status}
  </section>
  <section class=\"card\">
    <strong>Параметры шага</strong>
    <div class=\"help\">{description}</div>
    <form method=\"post\" action=\"/run/{step_index}\">
      {fields_html}
      <div class=\"actions\">
        <button type=\"submit\">Запустить шаг</button>
        <a class=\"btn-link secondary\" href=\"/step/{min(step_index + 1, len(STEPS) - 1)}\">Пропустить</a>
        <a class=\"btn-link secondary\" href=\"/reset\">Сбросить мастер</a>
      </div>
    </form>
  </section>
  <section class=\"card\" style=\"grid-column: 1 / -1;\">
    <strong>Вывод последнего запуска</strong>
    {output_html}
  </section>
</div>
"""
    return render_layout("Master Wizard", body)


def read_post_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8")
    data = parse_qs(raw)
    return {k: v[-1] for k, v in data.items()}


def build_prompt_map(step: dict, values: dict) -> list:
    prompt_map = []
    for prompt in step.get("prompts", []):
        field = prompt["field"]
        value = values.get(field, "")
        if prompt.get("field") in ("force_refresh", "overwrite_voiceover"):
            value = "y" if value in ("on", "y", "yes", True) else "n"
        prompt_map.append({
            "pattern": re.compile(prompt["pattern"]),
            "value": str(value) if value is not None else "",
            "required": prompt.get("required", False),
            "field": field,
        })
    return prompt_map


def run_step(step: dict, values: dict) -> tuple[int, str, str]:
    import fcntl
    import pty
    import select
    import subprocess

    cmd = [sys.executable, step["script"]]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        text=False,
    )
    os.close(slave_fd)

    fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)

    output_chunks = []
    prompt_map = build_prompt_map(step, values)
    answered = set()
    buffer = ""

    def maybe_answer():
        nonlocal buffer
        for idx, entry in enumerate(prompt_map):
            if idx in answered:
                continue
            if entry["pattern"].search(buffer):
                if entry["required"] and not entry["value"]:
                    raise RuntimeError(
                        f"Нет значения для обязательного поля: {entry['field']}"
                    )
                os.write(master_fd, (entry["value"] + "\n").encode("utf-8"))
                answered.add(idx)

    try:
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""
                if data:
                    text = data.decode("utf-8", errors="replace")
                    output_chunks.append(text)
                    buffer += text
                    if len(buffer) > 5000:
                        buffer = buffer[-5000:]
                    maybe_answer()
            if proc.poll() is not None:
                break
        # Drain remaining output
        while True:
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            output_chunks.append(text)
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    exit_code = proc.wait()
    output = "".join(output_chunks)
    summary = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • exit={exit_code}"
    return exit_code, output, summary


class WizardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            state = load_state()
            idx = state.get("current_step", 0)
            self.redirect(f"/step/{idx}")
            return
        if parsed.path.startswith("/step/"):
            try:
                step_index = int(parsed.path.split("/")[-1])
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if step_index < 0 or step_index >= len(STEPS):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            state = load_state()
            page = render_step_page(state, step_index)
            self.respond_html(page)
            return
        if parsed.path == "/reset":
            state = {
                "current_step": 0,
                "values": {},
                "steps": {},
            }
            save_state(state)
            self.redirect("/step/0")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/run/"):
            try:
                step_index = int(parsed.path.split("/")[-1])
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if step_index < 0 or step_index >= len(STEPS):
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            state = load_state()
            step = STEPS[step_index]
            form = read_post_body(self)

            # Persist values
            values = state.get("values", {})
            for field in step["fields"]:
                key = field["key"]
                if field.get("type") == "checkbox":
                    values[key] = "on" if key in form else ""
                else:
                    if key in form:
                        values[key] = form[key].strip()
            state["values"] = values

            # Run
            state.setdefault("steps", {})[step["id"]] = {
                "status": "running",
                "summary": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • запуск",
                "output": "",
            }
            save_state(state)

            try:
                exit_code, output, summary = run_step(step, values)
                status = "success" if exit_code == 0 else "failed"
                state["steps"][step["id"]] = {
                    "status": status,
                    "summary": summary,
                    "output": output,
                }
            except Exception as exc:
                state["steps"][step["id"]] = {
                    "status": "failed",
                    "summary": f"Ошибка: {exc}",
                    "output": state["steps"].get(step["id"], {}).get("output", ""),
                }
            save_state(state)

            next_step = min(step_index + 1, len(STEPS) - 1)
            state["current_step"] = next_step
            save_state(state)
            self.redirect(f"/step/{next_step}")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def respond_html(self, content: str):
        data = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path: str):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", path)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    host = os.environ.get("WIZARD_HOST", "127.0.0.1")
    port = int(os.environ.get("WIZARD_PORT", "8765"))
    server = HTTPServer((host, port), WizardHandler)
    print(f"Wizard running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
