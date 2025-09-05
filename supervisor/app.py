from datetime import datetime
import asyncio
from fastapi import FastAPI, WebSocket
import dotenv
import git, os
import requests

dotenv.load_dotenv()
GIT_USERNAME = os.getenv('GIT_USERNAME')
GIT_PASSWORD = os.getenv('GIT_PASSWORD')
MAIN_SERVER_PORT = os.getenv('MAIN_SERVER_PORT')

app = FastAPI()


@app.websocket("/ws/admin/update")
async def update_server_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("Checking authentication...")
    await asyncio.sleep(1)
    print("Authenticating...")
    res = requests.get(f"http://127.0.0.1:{MAIN_SERVER_PORT}/api/auth/profile/me", cookies=websocket.cookies)
    if res.status_code != 200 and res.json().get("role") != "Owner":
        await websocket.send_text("Unauthorized")
        await asyncio.sleep(1)
        await websocket.close()
        return
    await websocket.send_text("Authenticated")
    await asyncio.sleep(1)
    print("Pulling latest changes...")
    await websocket.send_text("Pulling latest changes...")
    await asyncio.sleep(1)
    repo = git.Repo("../")
    remote_url = repo.remotes.origin.url
    username = GIT_USERNAME
    password = GIT_PASSWORD
    if username and password:
        if remote_url.startswith("https://"):
            remote_url = remote_url.replace("https://", f"https://{username}:{password}@")
        elif remote_url.startswith("git@"):
            await websocket.send_text("Cannot authenticate SSH URLs with username/password. Use HTTPS instead.")
            await websocket.close()
            raise ValueError("Cannot authenticate SSH URLs with username/password. Use HTTPS instead.")

    try:
        resp = repo.git.pull(remote_url).splitlines()
    except Exception as err:
        err_list = str(err).splitlines()
        await websocket.send_text("<hr>")
        await websocket.send_text("\n".join(err_list))
        await websocket.send_text("\n<hr>")
        await websocket.send_text("Logging error...")
        await asyncio.sleep(1)
        for i in range(10):
            await asyncio.sleep(5)
            try:
                obj = {
                    "error_type": "Git Pull Failed",
                    "error_message": "Admin issued server update failed",
                    "error_traceback": "\n".join(err_list) + "\n\nExecuted by the supervisor",
                    "error_time": str(datetime.now()),
                    "error_severity": "low",
                }
                headers = dict(websocket.headers)
                headers["X-CSRFToken"] = websocket.cookies.get("csrftoken")
                res = requests.post(f"http://127.0.0.1:{MAIN_SERVER_PORT}/api/admin/log", cookies=websocket.cookies, headers=headers, json=obj)
                if res.status_code != 200:
                    await websocket.send_text("Error: Server response not OK")
                    await websocket.close()
                    return
                break
            except (Exception, KeyboardInterrupt) as err:
                await websocket.send_text("Error: Server not responding. \nRetrying...\n")
                print(err)
        else:
            await websocket.send_text("Fatal: Server is unresponsive")
            await websocket.close()
            return
        await websocket.send_text("Done")
        await websocket.close()
        return

    await websocket.send_text("<hr>")
    await websocket.send_text("\n".join(resp))
    await websocket.send_text("\n<hr>")
    await websocket.send_text("\nWaiting for the server to restart...")
    await asyncio.sleep(1)
    for i in range(10):
        await asyncio.sleep(5)
        try:
            obj = {
                "error_type": "Git Pull Succeeded",
                "error_message": "Admin issued server update succeeded",
                "error_traceback": "\n".join(resp) + "\n\nExecuted by the supervisor",
                "error_time": str(datetime.now()),
                "error_severity": "info",
            }
            headers = dict(websocket.headers)
            headers["X-CSRFToken"] = websocket.cookies.get("csrftoken")
            res = requests.post(f"http://127.0.0.1:{MAIN_SERVER_PORT}/api/admin/log", cookies=websocket.cookies, headers=headers, json=obj)
            if res.status_code != 200:
                await websocket.send_text("Error: Server response not OK")
                await websocket.close()
                return
            break
        except (Exception, KeyboardInterrupt) as err:
            await websocket.send_text("Error: Server not responding. \nRetrying...\n")
            print(err)
    else:
        await websocket.send_text("Fatal: Server is unresponsive")
        await websocket.close()
        return
    print("Done")
    await websocket.send_text("Done")
    await websocket.close()
