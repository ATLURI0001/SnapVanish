"""Preload the Naruto MP3 and play it without blocking video frames."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path


SOUND_PATH = Path(__file__).resolve().parent / "assets" / "vanish.MP3"


class VanishSound:
    def __init__(self, path: str | Path | None = None, volume: float = 1.0):
        if not path:
            path = SOUND_PATH
        path = Path(path)
        if not path.is_file():
            if path.suffix.lower() == ".mp3":
                alt_path = path.with_suffix(".mp3") if path.suffix == ".MP3" else path.with_suffix(".MP3")
                if alt_path.is_file():
                    path = alt_path
                else:
                    raise RuntimeError(f"Audio Naruto non trovato: {path}")
            else:
                raise RuntimeError(f"Audio Naruto non trovato: {path}")
        self.path = path

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        self.process = None
        self.ffplay = None
        self.sound = None
        self.owns_mixer = False
        self._closed = False
        self.volume = 1.0
        self.set_volume(volume)
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
            self.sound.set_volume(self.volume)
        except Exception as error:
            if self.owns_mixer:
                try:
                    mixer.quit()
                except Exception:
                    pass
                self.owns_mixer = False
            raise RuntimeError(f"Impossibile aprire l'audio Naruto: {error}") from error

    def set_volume(self, volume: float) -> None:
        """Set playback volume clamped between 0.0 and 1.0."""
        if not isinstance(volume, (int, float)) or isinstance(volume, bool) or not math.isfinite(volume):
            volume = 1.0
        self.volume = max(0.0, min(1.0, float(volume)))
        if self.sound is not None:
            try:
                self.sound.set_volume(self.volume)
            except Exception:
                pass

    def stop(self) -> None:
        """Stop active audio playback without closing resources."""
        if self.ffplay is not None:
            self._stop_process()
            return
        if self.sound is not None:
            try:
                self.sound.stop()
            except Exception:
                pass

    def is_playing(self) -> bool:
        """Return True if the sound is currently playing."""
        if self._closed:
            return False
        if self.ffplay is not None:
            return bool(self.process is not None and self.process.poll() is None)
        if self.sound is not None:
            try:
                return bool(self.sound.get_num_channels() > 0)
            except Exception:
                return False
        return False

    def _stop_process(self, timeout: float = 2.0) -> None:
        """Terminate any active ffplay child process and force-kill if it hangs."""
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            timeout = 2.0
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
        if self._closed:
            raise RuntimeError("Audio Naruto già chiuso.")
        if self.ffplay is not None:
            self._stop_process()
            cmd = [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet"]
            if self.volume < 1.0:
                cmd.extend(["-volume", str(int(round(self.volume * 100)))])
            cmd.extend(["-i", str(self.path)])
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as error:
                raise RuntimeError(f"Impossibile avviare l'audio Naruto: {error}") from error
            return
        if self.sound is None:
            raise RuntimeError("Audio Naruto non inizializzato.")
        self.sound.stop()
        if self.sound.play() is None:
            raise RuntimeError("Impossibile avviare l'audio Naruto: nessun canale libero.")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.ffplay is not None:
            self._stop_process()
            return
        if self.sound is not None:
            try:
                self.sound.stop()
            except Exception:
                pass
            self.sound = None
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

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
