from __future__ import annotations

import os
import time
import subprocess

from modules import timer
from modules import initialize_util
from modules import initialize

# GitHub 페이지에서 제공하는 설치 스크립트를 실행하는 함수를 정의합니다.
def run_install_script():
    install_script_url = "https://github.com/ninjaneural/webui/raw/main/install.sh"
    subprocess.run(["/bin/bash", "-c", f"$(curl -fsSL {install_script_url})"])

startup_timer = timer.startup_timer
startup_timer.record("launcher")

initialize.imports()

initialize.check_versions()

# API 생성 함수
def create_api(app):
    from modules.api.api import Api
    from modules.call_queue import queue_lock

    api = Api(app, queue_lock)
    return api

# API만 실행하는 함수
def api_only():
    from fastapi import FastAPI
    from modules.shared_cmd_options import cmd_opts

    initialize.initialize()

    app = FastAPI()
    initialize_util.setup_middleware(app)
    api = create_api(app)

    from modules import script_callbacks

    script_callbacks.before_ui_callback()
    script_callbacks.app_started_callback(None, app)

    print(f"Startup time: {startup_timer.summary()}.")
    api.launch(
        server_name="0.0.0.0",  # 모든 인터페이스에서 수신하도록 변경
        port=cmd_opts.port if cmd_opts.port else 7861,
        root_path=f"/{cmd_opts.subpath}" if cmd_opts.subpath else "",
    )

# 웹 UI 실행 함수
def webui():
    from modules.shared_cmd_options import cmd_opts

    launch_api = cmd_opts.api
    initialize.initialize()

    from modules import (
        shared,
        ui_tempdir,
        script_callbacks,
        ui,
        progress,
        ui_extra_networks,
    )

    while 1:
        if shared.opts.clean_temp_dir_at_start:
            ui_tempdir.cleanup_tmpdr()
            startup_timer.record("cleanup temp dir")

        script_callbacks.before_ui_callback()
        startup_timer.record("scripts before_ui_callback")

        shared.demo = ui.create_ui()
        startup_timer.record("create ui")

        app, local_url, share_url = shared.demo.launch(
            height=3000, prevent_thread_lock=True
        )

        startup_timer.record("gradio launch")

        # gradio의 CORS 정책을 수정합니다.
        app.user_middleware = [
            x for x in app.user_middleware if x.cls.__name__ != "CORSMiddleware"
        ]

        initialize_util.setup_middleware(app)

        progress.setup_progress_api(app)
        ui.setup_ui_api(app)

        if launch_api:
            create_api(app)

        ui_extra_networks.add_pages_to_demo(app)

        startup_timer.record("add APIs")

        with startup_timer.subcategory("app_started_callback"):
            script_callbacks.app_started_callback(shared.demo, app)

        timer.startup_record = startup_timer.dump()
        print(f"Startup time: {startup_timer.summary()}.")

        try:
            while True:
                server_command = shared.state.wait_for_server_command(timeout=5)
                if server_command:
                    if server_command in ("stop", "restart"):
                        break
                    else:
                        print(f"Unknown server command: {server_command}")
        except KeyboardInterrupt:
            print("Caught KeyboardInterrupt, stopping...")
            server_command = "stop"

        if server_command == "stop":
            print("Stopping server...")
            shared.demo.close()
            break

        # 브라우저에서 자동으로 웹 UI를 열지 않도록 설정합니다.
        os.environ.setdefault("SD_WEBUI_RESTARTING", "1")

        print("Restarting UI...")
        shared.demo.close()
        time.sleep(0.5)
        startup_timer.reset()
        script_callbacks.app_reload_callback()
        startup_timer.record("app reload callback")

# 설치 스크립트를 실행합니다.
run_install_script()

        script_callbacks.script_unloaded_callback()
        startup_timer.record("scripts unloaded callback")
        initialize.initialize_rest(reload_script_modules=True)


if __name__ == "__main__":
    from modules.shared_cmd_options import cmd_opts

    if cmd_opts.nowebui:
        api_only()
    else:
        webui()
