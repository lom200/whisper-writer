import subprocess
import os
import signal
import sys
import time
from typing import Optional

from pynput.keyboard import Controller as PynputController, Key as PynputKey

try:
    import pyperclip
except ImportError:  # pragma: no cover - pyperclip is an optional runtime dependency
    pyperclip = None

from utils import ConfigManager


def run_command_or_exit_on_failure(command):
    """
    Run a shell command and exit if it fails.

    Args:
        command (list): The command to run as a list of strings.
    """
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        exit(1)


class InputSimulator:
    """
    A class to simulate keyboard input using various methods.
    """

    def __init__(self):
        """
        Initialize the InputSimulator with the specified configuration.
        """
        self.input_method = ConfigManager.get_config_value('post_processing', 'input_method')
        self.dotool_process = None
        self.keyboard: Optional[PynputController] = None

        if self.input_method in ('pynput', 'clipboard'):
            self.keyboard = PynputController()
        elif self.input_method == 'dotool':
            self._initialize_dotool()

    def _initialize_dotool(self):
        """
        Initialize the dotool process for input simulation.
        """
        self.dotool_process = subprocess.Popen("dotool", stdin=subprocess.PIPE, text=True)
        assert self.dotool_process.stdin is not None

    def _terminate_dotool(self):
        """
        Terminate the dotool process if it's running.
        """
        if self.dotool_process:
            os.kill(self.dotool_process.pid, signal.SIGINT)
            self.dotool_process = None

    def typewrite(self, text):
        """
        Simulate typing the given text with the specified interval between keystrokes.

        Args:
            text (str): The text to type.
        """
        interval = ConfigManager.get_config_value('post_processing', 'writing_key_press_delay') or 0.0
        if self.input_method == 'pynput':
            self._typewrite_pynput(text, interval)
        elif self.input_method == 'clipboard':
            self._typewrite_clipboard(text, interval)
        elif self.input_method == 'ydotool':
            self._typewrite_ydotool(text, interval)
        elif self.input_method == 'dotool':
            self._typewrite_dotool(text, interval)

    def _typewrite_pynput(self, text, interval):
        """
        Simulate typing using pynput.

        Args:
            text (str): The text to type.
            interval (float): The interval between keystrokes in seconds.
        """
        if not self.keyboard:
            self.keyboard = PynputController()

        for char in text:
            self.keyboard.press(char)
            self.keyboard.release(char)
            time.sleep(interval)

    def _typewrite_clipboard(self, text, interval):
        """
        Paste text via the system clipboard, falling back to simulated typing on failure.
        """
        ConfigManager.console_print(f'Clipboard input: start len={len(text)} interval={interval}')
        if not self.keyboard:
            self.keyboard = PynputController()

        minimal_delay = max(interval, 0.02)
        modifier_key = self._clipboard_modifier_key()
        ConfigManager.console_print(f'Clipboard input: using paste delay {minimal_delay}s with modifier {modifier_key}')

        if pyperclip is None:
            ConfigManager.console_print('Clipboard input: pyperclip unavailable, falling back to typing')
            self._typewrite_pynput(text, interval)
            return

        try:
            previous_clipboard = pyperclip.paste()
            if previous_clipboard is None:
                ConfigManager.console_print('Clipboard input: unable to read previous clipboard (None)')
            elif previous_clipboard == text:
                ConfigManager.console_print('Clipboard input: previous clipboard already matches new text')
            else:
                ConfigManager.console_print(f'Clipboard input: captured previous clipboard len={len(previous_clipboard)}')
        except pyperclip.PyperclipException as exc:
            previous_clipboard = None
            ConfigManager.console_print(f'Clipboard input: failed to read clipboard ({exc}); proceeding without restore')

        try:
            pyperclip.copy(text)
            ConfigManager.console_print(f'Clipboard input: copied new text len={len(text)}')
        except pyperclip.PyperclipException as exc:
            ConfigManager.console_print(f'Clipboard input: failed to copy text ({exc}); falling back to typing')
            self._typewrite_pynput(text, interval)
            return

        time.sleep(minimal_delay)
        ConfigManager.console_print('Clipboard input: invoking paste hotkey')

        with self.keyboard.pressed(modifier_key):
            self.keyboard.press('v')
            self.keyboard.release('v')

        time.sleep(minimal_delay)
        ConfigManager.console_print('Clipboard input: post-paste delay complete')

        if previous_clipboard is not None and previous_clipboard != text:
            try:
                pyperclip.copy(previous_clipboard)
                ConfigManager.console_print('Clipboard input: previous clipboard restored')
            except pyperclip.PyperclipException as exc:
                ConfigManager.console_print(f'Clipboard input: failed to restore clipboard ({exc})')
        else:
            ConfigManager.console_print('Clipboard input: no clipboard restore necessary')

        ConfigManager.console_print('Clipboard input: completion path reached')

    def _clipboard_modifier_key(self):
        """Return the correct modifier key for paste on the current platform."""
        if sys.platform == 'darwin':
            return PynputKey.cmd
        return PynputKey.ctrl

    def _typewrite_ydotool(self, text, interval):
        """
        Simulate typing using ydotool.

        Args:
            text (str): The text to type.
            interval (float): The interval between keystrokes in seconds.
        """
        cmd = "ydotool"
        run_command_or_exit_on_failure([
            cmd,
            "type",
            "--key-delay",
            str(interval * 1000),
            "--",
            text,
        ])

    def _typewrite_dotool(self, text, interval):
        """
        Simulate typing using dotool.

        Args:
            text (str): The text to type.
            interval (float): The interval between keystrokes in seconds.
        """
        assert self.dotool_process and self.dotool_process.stdin
        self.dotool_process.stdin.write(f"typedelay {interval * 1000}\n")
        self.dotool_process.stdin.write(f"type {text}\n")
        self.dotool_process.stdin.flush()

    def cleanup(self):
        """
        Perform cleanup operations, such as terminating the dotool process.
        """
        if self.input_method == 'dotool':
            self._terminate_dotool()
