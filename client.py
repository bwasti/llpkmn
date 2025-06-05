import socket
import time
import sys
import os
from datetime import datetime # Import datetime module

# Configuration
HOST = '127.0.0.1'  # Or the IP address of the machine running mGBA if not local
PORT = 8888         # Default port - **CHECK YOUR MGBA CONSOLE FOR THE ACTUAL PORT**
TERMINATION_MARKER = b'<|END|>' # The marker needs to be in bytes for socket communication
BUFFER_SIZE = 1024  # How much data to receive at once

def send_command(sock, command):
    """Sends a command string to the server and receives the response."""
    full_command_bytes = command.encode('utf-8') + TERMINATION_MARKER

    try:
        sock.sendall(full_command_bytes)
        print(f"Sent: {command}")

        # Receive the response - potentially in chunks
        buffer = b""
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                print("Server closed the connection unexpectedly.")
                return None
            buffer += chunk

            # Check if the termination marker is in the buffer
            if TERMINATION_MARKER in buffer:
                response_bytes, _, remainder = buffer.partition(TERMINATION_MARKER)
                response_str = response_bytes.decode('utf-8')
                # print(f"Received Raw: {response_str!r}") # Debug print
                return response_str.strip() # Return the response, stripping whitespace
                # Note: If remainder contains start of next message,
                # a more complex client would need to handle it.
                # For this simple script, we assume one command-response cycle.

    except socket.error as e:
        print(f"Socket error during command sending: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None


def tap_button(sock, button_name):
    """Sends a command to tap a specific button."""
    command = f"mgba-http.button.tap,{button_name}"
    response = send_command(sock, command)
    #if response is not None:
    #    print(f"Response for tapping {button_name}: {response}")

def take_screenshot(sock, screenshot_dir):
    # Create the directory if it doesn't exist
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        #print(f"Ensured screenshot directory exists: {screenshot_dir}")
    except OSError as e:
        print(f"Error creating screenshot directory {screenshot_dir}: {e}", file=sys.stderr)
        return # Cannot proceed if directory creation fails

    # Generate a unique filename using a timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"

    # Construct the full local path
    local_screenshot_path = os.path.join(screenshot_dir, filename)

    # **Important:** For the path sent to the Lua script, use forward slashes
    # as backslashes might be interpreted as escape characters in Lua.
    # This assumes the mGBA host OS can handle forward slashes in paths, which is common.
    lua_compatible_path = local_screenshot_path.replace('\\', '/')

    #print(f"Requesting screenshot be saved to: {local_screenshot_path}")

    # Construct the command for the Lua server
    command = f"core.screenshot,{lua_compatible_path}"

    # Send the command and get the response
    response = send_command(sock, command)

    #if response is not None:
    #    print(f"Response for screenshot request: {response}")
    #    if response == "<|SUCCESS|>":
    #        print(f"Screenshot successfully triggered. Check '{local_screenshot_path}' on the mGBA host.")
    #    else:
    #        print(f"Screenshot command returned an unexpected response: {response}")


def main():
    """Connects to the server and sends test button commands + screenshot."""
    print(f"Attempting to connect to {HOST}:{PORT}...")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((HOST, PORT))
        print("Connection successful.")

        # Optional: Send an initial ACK message as seen handled by the server script
        send_command(client_socket, "<|ACK|>")
        time.sleep(0.1) # Give the server a moment to process

        print("\nSending button tap commands:")

        # Send Up, Down, Left, Right taps with small delays
        tap_button(client_socket, "Up")
        time.sleep(0.5) # Pause to see the effect in the emulator

        tap_button(client_socket, "Down")
        time.sleep(0.5)

        tap_button(client_socket, "Left")
        time.sleep(0.5)

        tap_button(client_socket, "Right")
        time.sleep(0.5)

        print("\nRequesting screenshot...")
        time.sleep(0.5) # Give a moment after button presses
        script_dir = os.getcwd() # Gets the current working directory
        screenshot_dir = os.path.join(script_dir, "screenshots")
        take_screenshot(client_socket, screenshot_dir)

        print("\nFinished sending commands.")

    except ConnectionRefusedError:
        print(f"Connection refused. Make sure the mGBA script is running and listening on port {PORT}.", file=sys.stderr)
        print("Check the mGBA console when loading the script to verify the exact port number.", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
    finally:
        print("Closing socket connection.")
        client_socket.close()

if __name__ == "__main__":
    main()
