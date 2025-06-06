import json
import base64
import time
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal
from client import *
from pathlib import Path
from enum import Enum

##################
# Connect to LLM #
##################
host = os.getenv("HOST", "127.0.0.1:8080")
print(f"Connecting to host {host}...")
# client = OpenAI(base_url=f"http://{host}/v1", api_key="sk-test", timeout=9999)
client = OpenAI(
    api_key="feather-dont-need-no-stinkin-api-key",
    base_url="http://localhost:8082/v1",
    timeout=999,
)

###################
# Connect to mGBA #
###################
mgba_host = os.getenv("MGBA_HOST", "127.0.0.1")
mgba_port = int(os.getenv("MGBA_PORT", "8888"))
print(f"Connecting to mGBA at {mgba_host}, port {mgba_port}")

TERMINATION_MARKER = b"<|END|>"
BUFFER_SIZE = 1024

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((mgba_host, mgba_port))
send_command(client_socket, "<|ACK|>")
time.sleep(1)

########################
# Setup screenshot dir #
########################
script_dir = os.getcwd()
screenshot_dir = os.getenv("SCREENSHOT_DIR", os.path.join(script_dir, "screenshots"))
print(f"Screenshots being saved to {screenshot_dir}")

############
# Settings #
############
history_limit = int(os.getenv("HISTORY_LIMIT", "1"))
# -1 == no stopping
max_steps = int(os.getenv("MAX_STEPS", "-1"))


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_n_latest_pngs(directory, n=1):
    path = Path(directory)
    png_files = list(path.glob("*.png"))
    if not png_files:
        return []

    sorted_pngs = sorted(png_files, key=lambda p: p.stat().st_mtime, reverse=True)
    return sorted_pngs[:n]


# the Select, R, and L keys are super rare to use. we can prune them to help the model out
# keys = ["A","B","Select","Start","Right","Left","Up","Down","R","L"]
keys = ["A", "B", "Right", "Left", "Up", "Down", "Start"]


def get_opinion_msg(client):
    take_screenshot(client_socket, screenshot_dir)
    png = get_n_latest_pngs(screenshot_dir, 1)[-1]
    img = encode_image(png)
    content = []
    content.append(
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}
    )
    content.append(
        {
            "type": "text",
            "text": f"Look at this most recent image.  It is the current game state.  In plain but detailed English, think about and describe what our immediate next step should be to achieve our goal.  Be pragmatic and conclude which button we should press (the options are {keys}).",
        }
    )
    return {"role": "user", "content": content}


def get_button_msg(client):
    content = []
    content.append(
        {
            "type": "text",
            "text": f"Now, given the above reasoning, choose the appropriate button to press in this current instance.  To go through doors, stand in front of them and press up.  To interact with people, press A.  Don't get stuck repeating the same thing!  You must respond with a valid button from this list: {keys}",
        }
    )
    return {"role": "user", "content": content}


class GBAButtonResponse(BaseModel):
    button: Literal["A", "B", "Right", "Left", "Up", "Down", "Start"]


sys_prompt = """
You are playing Pokemon Emerald on game boy advanced.  You control the character in the middle of the screen.  Your general task is to walk around in the tall grass and train pokemon!  Fight every pokemon you encounter in the grass.  Fights are triggered randomly when walking.
"""

if __name__ == "__main__":
    #############
    # Main loop #
    #############
    # history = []
    messages = [
        {"role": "system", "content": sys_prompt},
    ]
    while max_steps != 0:
        if max_steps > 0:
            max_steps -= 1
        # 1. Describe the strategy
        msg = get_opinion_msg(client)
        messages.append(msg)
        response = client.chat.completions.create(
            model="feather", top_p=0.9, temperature=0.6, messages=messages
        )
        rm = response.choices[0].message
        messages.append({"role": rm.role, "content": rm.content})
        print(rm.content)
        # 2. Now pick a button
        msg = get_button_msg(client)
        messages.append(msg)
        response = client.beta.chat.completions.parse(
            model="feather",
            temperature=0.6,
            messages=messages,
            response_format=GBAButtonResponse,
        )
        rm = response.choices[0].message
        button = rm.content
        button = json.loads(button)["button"]
        messages.append({"role": rm.role, "content": button})
        tap_button(client_socket, button)
        messages.append(response.choices[0].message)
