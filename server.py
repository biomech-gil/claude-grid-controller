#!/usr/bin/env python3
"""tmux Claude Code Control Panel Server"""

import http.server
import json
import subprocess
import os
import datetime
import threading
import time
import re
from urllib.parse import urlparse

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
TMUX_SESSION = "work"
WINDOW_INDEX = 1

current_project = {
    "project_id": None, "rows": 0, "cols": 0,
    "pane_count": 0, "created_at": None, "setup_status": "idle",
}
lock = threading.Lock()


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def get_project_dir(project_id):
    return os.path.join(PROJECTS_DIR, project_id)


def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_to_pane_file(project_id, pane_id, entry_type, message):
    if not project_id:
        return
    project_dir = get_project_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    log_path = os.path.join(project_dir, f"node_{pane_id}.log")
    ts = timestamp()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {entry_type}: {message}\n")


def tmux_send_keys(pane_id, text):
    target = f"{TMUX_SESSION}:{WINDOW_INDEX}.{pane_id}"
    log(f"SEND-KEYS to {target}: {text[:80]}")
    result = subprocess.run(
        ["tmux", "send-keys", "-t", target, text, "Enter"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log(f"SEND-KEYS ERROR: {result.stderr}")
    return result.returncode == 0


def tmux_capture_pane(pane_id, lines=50):
    target = f"{TMUX_SESSION}:{WINDOW_INDEX}.{pane_id}"
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def tmux_list_panes():
    result = subprocess.run(
        ["tmux", "list-panes", "-t", TMUX_SESSION, "-F", "#{pane_index}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log(f"LIST-PANES ERROR: {result.stderr}")
        return []
    panes = [int(idx.strip()) for idx in result.stdout.strip().split("\n") if idx.strip()]
    return panes


def create_tmux_session(rows, cols):
    total_panes = rows * cols
    log(f"CREATE SESSION: {rows}x{cols} = {total_panes} panes")

    subprocess.run(["tmux", "kill-server"], capture_output=True, text=True)
    log("Killed tmux server")
    time.sleep(2)

    # Build shell script with && chain (proven to work)
    parts = [f"tmux new-session -d -s {TMUX_SESSION} -x 300 -y 80"]
    for i in range(total_panes - 1):
        parts.append(f"tmux split-window -t {TMUX_SESSION} && tmux select-layout -t {TMUX_SESSION} tiled")

    script_content = "#!/bin/bash\n" + " && ".join(parts) + "\n"
    script_path = os.path.join(BASE_DIR, "_tmux_setup.sh")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)

    log(f"Running setup script ({total_panes} panes)...")
    result = subprocess.run(["bash", script_path], capture_output=True, text=True, timeout=30)
    log(f"Script result: rc={result.returncode}")
    if result.stderr:
        log(f"Script stderr: {result.stderr[:300]}")

    time.sleep(2)
    panes = tmux_list_panes()
    log(f"Panes created: {len(panes)} -> {panes}")

    try:
        os.remove(script_path)
    except OSError:
        pass

    return len(panes)


def start_claude_in_panes(pane_ids):
    log(f"Starting claude in {len(pane_ids)} panes: {pane_ids}")
    for pane_id in pane_ids:
        tmux_send_keys(pane_id, "claude --dangerously-skip-permissions")
        time.sleep(0.3)
    log("Claude start commands sent")


def send_trust_prompt(pane_ids):
    log("Waiting 10s for claude to load...")
    time.sleep(10)
    log("Sending Enter to accept trust prompt on all panes...")
    for pane_id in pane_ids:
        target = f"{TMUX_SESSION}:{WINDOW_INDEX}.{pane_id}"
        subprocess.run(
            ["tmux", "send-keys", "-t", target, "", "Enter"],
            capture_output=True, text=True,
        )
        time.sleep(0.5)
    log("Trust prompt accepted on all panes")


class TMUXHandler(http.server.BaseHTTPRequestHandler):

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def read_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.serve_index()
            elif path == "/api/outputs":
                self.handle_get_outputs()
            elif path == "/api/projects":
                self.handle_get_projects()
            elif path == "/api/status":
                self.handle_get_status()
            elif path.startswith("/api/output/"):
                pane_id = path.split("/")[-1]
                self.handle_get_pane_output(int(pane_id))
            else:
                self.send_error_json("Not found", 404)
        except Exception as e:
            log(f"GET ERROR: {e}")
            self.send_error_json(str(e), 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/start":
                self.handle_start()
            elif path == "/api/send":
                self.handle_send()
            elif path == "/api/send-all":
                self.handle_send_all()
            elif path == "/api/restore":
                self.handle_restore()
            else:
                self.send_error_json("Not found", 404)
        except Exception as e:
            log(f"POST ERROR: {e}")
            self.send_error_json(str(e), 500)

    def serve_index(self):
        index_path = os.path.join(BASE_DIR, "index.html")
        if not os.path.exists(index_path):
            self.send_error_json("index.html not found", 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()
        with open(index_path, "rb") as f:
            self.wfile.write(f.read())

    def handle_get_outputs(self):
        panes = tmux_list_panes()
        outputs = {}
        for pane_id in panes:
            outputs[str(pane_id)] = tmux_capture_pane(pane_id)
        self.send_json({"outputs": outputs, "panes": panes})

    def handle_get_projects(self):
        ensure_projects_dir()
        projects = []
        for name in sorted(os.listdir(PROJECTS_DIR), reverse=True):
            project_path = os.path.join(PROJECTS_DIR, name)
            if os.path.isdir(project_path):
                config_path = os.path.join(project_path, "config.json")
                config = {}
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                projects.append({"project_id": name, "config": config})
        self.send_json({"projects": projects})

    def handle_get_status(self):
        with lock:
            info = dict(current_project)
        panes = tmux_list_panes()
        info["active_panes"] = panes
        info["active_pane_count"] = len(panes)
        self.send_json(info)

    def handle_get_pane_output(self, pane_id):
        output = tmux_capture_pane(pane_id)
        self.send_json({"pane_id": pane_id, "output": output})

    def handle_start(self):
        body = self.read_body()
        rows = int(body.get("rows", 3))
        cols = int(body.get("cols", 3))
        pane_count = rows * cols
        log(f"=== API START: {rows}x{cols} = {pane_count} ===")

        now = datetime.datetime.now()
        project_id = now.strftime("%Y%m%d_%H%M%S")
        project_dir = get_project_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)

        config = {"rows": rows, "cols": cols, "created_at": now.isoformat(), "pane_count": pane_count}
        with open(os.path.join(project_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        with lock:
            current_project.update({
                "project_id": project_id, "rows": rows, "cols": cols,
                "pane_count": pane_count, "created_at": now.isoformat(),
                "setup_status": "creating_panes",
            })

        def setup_tmux():
            try:
                actual = create_tmux_session(rows, cols)
                with lock:
                    current_project["setup_status"] = f"starting_claude ({actual} panes)"

                pane_ids = tmux_list_panes()
                if not pane_ids:
                    log("ERROR: No panes found after creation!")
                    with lock:
                        current_project["setup_status"] = "error: no panes created"
                    return

                start_claude_in_panes(pane_ids)
                with lock:
                    current_project["setup_status"] = "waiting_trust"

                send_trust_prompt(pane_ids)
                with lock:
                    current_project["setup_status"] = "ready"
                log("=== SETUP COMPLETE ===")
            except Exception as e:
                log(f"SETUP ERROR: {e}")
                import traceback
                traceback.print_exc()
                with lock:
                    current_project["setup_status"] = f"error: {e}"

        t = threading.Thread(target=setup_tmux, daemon=True)
        t.start()

        self.send_json({
            "status": "starting", "project_id": project_id,
            "rows": rows, "cols": cols, "pane_count": pane_count,
        })

    def handle_send(self):
        body = self.read_body()
        panes = body.get("panes", [])
        message = body.get("message", "")
        log(f"API SEND: panes={panes} msg={message[:80]}")

        if not message:
            self.send_error_json("message is required")
            return
        if not panes:
            self.send_error_json("panes list is required")
            return

        with lock:
            pid = current_project["project_id"]

        results = []
        for pane_id in panes:
            pane_id = int(pane_id)
            ok = tmux_send_keys(pane_id, message)
            log_to_pane_file(pid, pane_id, "INPUT", message)
            results.append({"pane_id": pane_id, "status": "sent" if ok else "error"})
        self.send_json({"results": results})

    def handle_send_all(self):
        body = self.read_body()
        message = body.get("message", "")
        log(f"API SEND-ALL: msg={message[:80]}")

        if not message:
            self.send_error_json("message is required")
            return

        panes = tmux_list_panes()
        if not panes:
            self.send_error_json("No active panes")
            return

        with lock:
            pid = current_project["project_id"]

        results = []
        for pane_id in panes:
            ok = tmux_send_keys(pane_id, message)
            log_to_pane_file(pid, pane_id, "INPUT", message)
            results.append({"pane_id": pane_id, "status": "sent" if ok else "error"})
        self.send_json({"results": results, "pane_count": len(panes)})

    def handle_restore(self):
        body = self.read_body()
        project_id = body.get("project_id", "")
        log(f"API RESTORE: {project_id}")

        if not project_id:
            self.send_error_json("project_id is required")
            return

        project_dir = get_project_dir(project_id)
        config_path = os.path.join(project_dir, "config.json")
        if not os.path.exists(config_path):
            self.send_error_json(f"Project {project_id} not found")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        rows, cols = config["rows"], config["cols"]
        pane_count = config["pane_count"]

        pane_logs = {}
        for pid in range(1, pane_count + 1):
            log_path = os.path.join(project_dir, f"node_{pid}.log")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    inputs = []
                    for line in f:
                        match = re.match(r"\[.*?\] INPUT: (.+)", line.strip())
                        if match:
                            inputs.append(match.group(1))
                    pane_logs[pid] = inputs

        now = datetime.datetime.now()
        new_project_id = now.strftime("%Y%m%d_%H%M%S")
        new_project_dir = get_project_dir(new_project_id)
        os.makedirs(new_project_dir, exist_ok=True)

        new_config = {
            "rows": rows, "cols": cols, "created_at": now.isoformat(),
            "pane_count": pane_count, "restored_from": project_id,
        }
        with open(os.path.join(new_project_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=2)

        with lock:
            current_project.update({
                "project_id": new_project_id, "rows": rows, "cols": cols,
                "pane_count": pane_count, "created_at": now.isoformat(),
                "setup_status": "restoring",
            })

        def restore_tmux():
            try:
                create_tmux_session(rows, cols)
                pane_ids = tmux_list_panes()
                start_claude_in_panes(pane_ids)
                send_trust_prompt(pane_ids)
                time.sleep(5)

                for pid in pane_ids:
                    if pid in pane_logs and pane_logs[pid]:
                        context = "Previous conversation:\n" + "\n".join(pane_logs[pid][-10:])
                        tmux_send_keys(pid, context)
                        log_to_pane_file(new_project_id, pid, "INPUT", context)
                        time.sleep(0.5)

                with lock:
                    current_project["setup_status"] = "ready"
                log("Restore complete!")
            except Exception as e:
                log(f"RESTORE ERROR: {e}")
                with lock:
                    current_project["setup_status"] = f"error: {e}"

        t = threading.Thread(target=restore_tmux, daemon=True)
        t.start()

        self.send_json({
            "status": "restoring", "original_project": project_id,
            "new_project_id": new_project_id, "rows": rows, "cols": cols,
        })

    def log_message(self, format, *args):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] HTTP {self.address_string()} - {format % args}", flush=True)


class ThreadedHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    ensure_projects_dir()
    server = ThreadedHTTPServer(("0.0.0.0", PORT), TMUXHandler)
    log(f"Server starting on http://0.0.0.0:{PORT}")
    log(f"Projects: {PROJECTS_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
