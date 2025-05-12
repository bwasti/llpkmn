import json
import base64
import time
from openai import OpenAI
from client import *
from pathlib import Path

##################
# Connect to LLM #
##################
host = os.getenv("HOST", "127.0.0.1:8080")
print(f"Connecting to host {host}...")
client = OpenAI(base_url=f"http://{host}/v1", api_key="sk-test", timeout=9999)

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
history_limit = int(os.getenv("HISTORY_LIMIT", "8"))
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


prompt = """
You are tasked with healing all the Pokemon in your party. Given the history provided, what button would you press now?

The options are {keys}.

Think about your answer out loud, and then conclude with a single button. (The button must be the final word or we cannot parse it.)
"""
prompt = os.getenv("PROMPT", prompt)
print(f'Base prompt for the model:\n\n"""\n{prompt}\n"""')

# the Select, R, and L keys are super rare to use. we can prune them to help the model out
# keys = ["A","B","Select","Start","Right","Left","Up","Down","R","L"]
keys = ["A", "B", "Start", "Right", "Left", "Up", "Down"]


def parse_action(s):
    s_orig = s
    s = s.replace(".", "")
    s = s.lower()
    s = s.split(" ")[-1]
    for key in keys:
        if key.lower() in s:
            return key
    raise Exception("Invalid action" + s_orig)


def construct_prompt(hist_actions, hist_imgs):
    assert len(hist_actions) == (
        len(hist_imgs) - 1
    ), f"{len(hist_actions)=}, {len(hist_imgs)=}"

    content = []
    content.append(
        {"type": "text", "text": f"We started our game state with the following:"}
    )
    first_img = hist_imgs[0]
    content.append(
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{first_img}"},
        }
    )
    for hist, img in zip(hist_actions, hist_imgs[1:]):
        content.append(
            {
                "type": "text",
                "text": f"This was your response at the time: {hist}, yielding the following game state:",
            }
        )
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}
        )
    content.append({"type": "text", "text": prompt.format(keys=keys)})
    return content


def take_action(client, history):
    take_screenshot(client_socket, screenshot_dir)
    pngs = get_n_latest_pngs(screenshot_dir, len(history) + 1)
    imgs = [encode_image(png) for png in pngs]
    content = construct_prompt(history, imgs)
    resp = get_response(content)
    action = parse_action(resp)
    tap_button(client_socket, action)
    time.sleep(1)
    return resp


def get_response(content):
    messages = [{"role": "user", "content": content}]
    response = client.chat.completions.create(
        model="feather", temperature=0.0, stream=True, messages=messages
    )
    acc = ""
    for chunk in response:
        d = chunk.choices[0].delta.content
        if d == None:
            break
        print(d, end="")
        acc += d
    print("\n")
    return acc


if __name__ == "__main__":
    #############
    # Main loop #
    #############
    history = []
    while max_steps != 0:
        if max_steps > 0:
            max_steps -= 1
        history.append(take_action(client_socket, history[-history_limit:]))
