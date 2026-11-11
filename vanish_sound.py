"""Preload the Naruto MP3 and play it without blocking video frames."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


SOUND_PATH = Path(__file__).resolve().parent / "assets" / "vanish.MP3"


class VanishSound:
    def __init__(self, path: Path = SOUND_PATH):
        if not path.is_file():
            alt_path = path.with_suffix(".mp3") if path.suffix == ".MP3" else path.with_suffix(".MP3")
            if alt_path.is_file():
                path = alt_path
            else:
                raise RuntimeError(f"Audio Naruto non trovato: {path}")
        self.path = path

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        self.process = None
        self.ffplay = None
        try:
            from pygame import mixer
        except ImportError:
            self.ffplay = shutil.which("ffplay")
            if self.ffplay is None:
                raise RuntimeError("Per riprodurre vanish.MP3 installa pygame o ffplay.")
            return

        self.mixer = mixer
        self.owns_mixer = mixer.get_init() is None
        try:
            if self.owns_mixer:
                mixer.init(frequency=44100, size=-16, channels=2, buffer=256)
            self.sound = mixer.Sound(str(path))  # Decode once, before opening the webcam.
        except Exception as error:
            if self.owns_mixer:
                try:
                    mixer.quit()
                except Exception:
                    pass
            raise RuntimeError(f"Impossibile aprire l'audio Naruto: {error}") from error

    def _stop_process(self, timeout: float = 2.0) -> None:
        """Terminate any active ffplay child process and force-kill if it hangs."""
        proc = self.process
        self.process = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    pass
            except (ProcessLookupError, OSError):
                pass

    def play(self) -> None:
        if self.ffplay is not None:
            self._stop_process()
            try:
                self.process = subprocess.Popen(
                    [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet",
                     "-i", str(self.path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as error:
                raise RuntimeError(f"Impossibile avviare l'audio Naruto: {error}") from error
            return
        self.sound.stop()
        if self.sound.play() is None:
            raise RuntimeError("Impossibile avviare l'audio Naruto: nessun canale libero.")

    def close(self) -> None:
        if self.ffplay is not None:
            self._stop_process()
            return
        if self.owns_mixer:
            try:
                self.mixer.quit()
            except Exception:
                pass
            self.owns_mixer = False

    def __enter__(self) -> "VanishSound":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
