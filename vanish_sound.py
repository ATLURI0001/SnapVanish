"""Preload the Naruto MP3 and play it without blocking video frames."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


SOUND_PATH = Path(__file__).resolve().parent / "assets" / "vanish.MP3"
PAN_LAWS = ("linear", "constant_power")


def compute_stereo_gains(pan: float, volume: float, law: str = "linear") -> tuple[float, float]:
    """Compute left and right channel gains for stereo panning.

    Supports:
      - 'linear': balance-style clamped linear attenuation (default, backward compatible).
      - 'constant_power': equal-power sine/cosine law preserving acoustic energy L^2 + R^2 = V^2.
    """
    if not isinstance(pan, (int, float)) or isinstance(pan, bool) or not math.isfinite(pan):
        pan = 0.0
    if not isinstance(volume, (int, float)) or isinstance(volume, bool) or not math.isfinite(volume):
        volume = 1.0
    p = max(-1.0, min(1.0, float(pan)))
    v = max(0.0, min(1.0, float(volume)))
    if law == "constant_power":
        theta = (p + 1.0) * (math.pi / 4.0)
        return round(math.cos(theta) * v, 6), round(math.sin(theta) * v, 6)
    left = max(0.0, min(1.0, 1.0 - p)) * v
    right = max(0.0, min(1.0, 1.0 + p)) * v
    return left, right


class VanishSound:
    def __init__(
        self,
        path: str | Path | None = None,
        volume: float = 1.0,
        min_trigger_interval_ms: int = 0,
        pan_law: str = "linear",
        clock: Callable[[], float] | None = None,
    ):
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
        self._lock = threading.RLock()
        self._clock: Callable[[], float] = clock if callable(clock) else time.monotonic
        self._cooldown_ms = 0
        self._pan_law = "linear"
        self._last_play_ts: float | None = None
        self._play_count = 0
        self._suppressed_count = 0
        self.process = None
        self.ffplay = None
        self.sound = None
        self.channel = None
        self._paused = False
        self._pan = 0.0
        self.owns_mixer = False
        self._closed = False
        self.volume = 1.0
        self.set_volume(volume)
        self.set_cooldown(min_trigger_interval_ms)
        self.set_pan_law(pan_law)
        self._pre_mute_volume = self.volume if self.volume > 0.0 else 1.0
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

    def get_volume(self) -> float:
        """Return current volume level between 0.0 and 1.0."""
        return self.volume

    def set_volume_db(self, db: float) -> None:
        """Set playback volume from decibels clamped between -60.0 dB and 0.0 dB."""
        if not isinstance(db, (int, float)) or isinstance(db, bool) or not math.isfinite(db):
            db = 0.0
        clamped_db = max(-60.0, min(0.0, float(db)))
        if clamped_db <= -60.0:
            self.set_volume(0.0)
        else:
            self.set_volume(round(10.0 ** (clamped_db / 20.0), 4))

    def get_volume_db(self) -> float:
        """Return current volume level expressed in decibels (-60.0 dB to 0.0 dB)."""
        if self.volume <= 0.001:
            return -60.0
        return round(20.0 * math.log10(self.volume), 2)

    def mute(self) -> None:
        """Mute audio playback while preserving previous volume level."""
        if self.volume > 0.0:
            self._pre_mute_volume = self.volume
        self.set_volume(0.0)

    def unmute(self) -> None:
        """Restore previous volume level prior to muting."""
        restore = self._pre_mute_volume if self._pre_mute_volume > 0.0 else 1.0
        self.set_volume(restore)

    @property
    def is_muted(self) -> bool:
        """Return True if playback volume is currently muted to 0.0."""
        return bool(self.volume == 0.0)

    def get_length(self) -> float:
        """Return length of loaded audio in seconds, or 0.0 if unknown/unavailable."""
        if self.sound is not None:
            try:
                length = float(self.sound.get_length())
                return length if math.isfinite(length) and length >= 0.0 else 0.0
            except Exception:
                return 0.0
        return 0.0

    @property
    def is_closed(self) -> bool:
        """Return True if sound engine or child process has been closed."""
        return self._closed

    def stop(self) -> None:
        """Stop active audio playback without closing resources."""
        self._paused = False
        self.channel = None
        if self.ffplay is not None:
            self._stop_process()
            return
        if self.sound is not None:
            try:
                self.sound.stop()
            except Exception:
                pass

    def pause(self) -> None:
        """Pause audio playback on active sound channel."""
        if self.channel is not None:
            try:
                self.channel.pause()
            except Exception:
                pass
        self._paused = True

    def unpause(self) -> None:
        """Resume playback on active sound channel."""
        if self.channel is not None:
            try:
                self.channel.unpause()
            except Exception:
                pass
        self._paused = False

    @property
    def is_paused(self) -> bool:
        """Return True if playback is currently paused."""
        return self._paused

    def set_pan(self, pan: float) -> None:
        """Set stereo panning balance between -1.0 (left) and 1.0 (right)."""
        with self._lock:
            if not isinstance(pan, (int, float)) or isinstance(pan, bool) or not math.isfinite(pan):
                pan = 0.0
            self._pan = max(-1.0, min(1.0, float(pan)))
            self._apply_pan()

    def get_pan(self) -> float:
        """Return current stereo panning level between -1.0 and 1.0."""
        with self._lock:
            return self._pan

    def set_pan_law(self, law: str) -> None:
        """Select stereo panning law ('linear' or 'constant_power')."""
        with self._lock:
            if law not in PAN_LAWS:
                raise ValueError(f"Unsupported pan law '{law}'. Expected one of {PAN_LAWS}.")
            self._pan_law = law
            self._apply_pan()

    def get_pan_law(self) -> str:
        """Return active stereo panning law."""
        with self._lock:
            return self._pan_law

    def set_cooldown(self, interval_ms: int) -> None:
        """Set minimum debounce interval between consecutive play() triggers in milliseconds."""
        with self._lock:
            if not isinstance(interval_ms, int) or isinstance(interval_ms, bool) or interval_ms < 0:
                interval_ms = 0
            self._cooldown_ms = min(60000, interval_ms)

    def get_cooldown(self) -> int:
        """Return active trigger cooldown window in milliseconds."""
        with self._lock:
            return self._cooldown_ms

    def get_telemetry(self) -> dict[str, object]:
        """Return thread-safe runtime diagnostics snapshot for audio engine observability."""
        with self._lock:
            return {
                "backend": "ffplay" if self.ffplay is not None else "pygame",
                "play_count": self._play_count,
                "suppressed_count": self._suppressed_count,
                "last_play_monotonic": self._last_play_ts,
                "cooldown_ms": self._cooldown_ms,
                "pan": self._pan,
                "pan_law": self._pan_law,
                "volume": self.volume,
                "volume_db": self.get_volume_db(),
                "is_muted": self.is_muted,
                "is_paused": self._paused,
                "is_closed": self._closed,
            }

    def _apply_pan(self) -> None:
        """Apply stereo channel panning to active channel using active pan law."""
        if self.channel is not None:
            left, right = compute_stereo_gains(self._pan, self.volume, law=self._pan_law)
            try:
                self.channel.set_volume(left, right)
            except Exception:
                pass

    def fade_out(self, duration_ms: int = 300) -> None:
        """Fade out active audio playback over duration_ms milliseconds."""
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0:
            duration_ms = 300
        duration_ms = min(10000, duration_ms)
        if self.ffplay is not None:
            self._stop_process()
            return
        if self.sound is not None:
            try:
                self.sound.fadeout(duration_ms)
            except Exception:
                pass

    def fade_in(self, duration_ms: int = 300, loops: int = 0) -> None:
        """Fade in audio playback over duration_ms milliseconds."""
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0:
            duration_ms = 300
        duration_ms = min(10000, duration_ms)
        self.play(loops=loops, fade_ms=duration_ms)

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

    def play(self, loops: int = 0, fade_ms: int = 0, force: bool = False) -> bool:
        with self._lock:
            if self._closed:
                raise RuntimeError("Audio Naruto già chiuso.")
            if not isinstance(loops, int) or isinstance(loops, bool):
                loops = 0
            loops = max(-1, min(100, loops))
            if not isinstance(fade_ms, int) or isinstance(fade_ms, bool) or fade_ms < 0:
                fade_ms = 0
            fade_ms = min(10000, fade_ms)

            now = self._clock()
            if (
                not force
                and self._cooldown_ms > 0
                and self._last_play_ts is not None
                and (now - self._last_play_ts) * 1000.0 < self._cooldown_ms
            ):
                self._suppressed_count += 1
                return False

            if self.ffplay is not None:
                self._stop_process()
                cmd = [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet"]
                if loops == -1:
                    cmd.extend(["-loop", "0"])
                elif loops > 0:
                    cmd.extend(["-loop", str(loops + 1)])
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
                self._last_play_ts = now
                self._play_count += 1
                return True
            if self.sound is None:
                raise RuntimeError("Audio Naruto non inizializzato.")
            self.sound.stop()
            if fade_ms > 0:
                channel = self.sound.play(loops=loops, fade_ms=fade_ms)
            else:
                channel = self.sound.play(loops=loops)
            if channel is None:
                raise RuntimeError("Impossibile avviare l'audio Naruto: nessun canale libero.")
            self.channel = channel
            self._paused = False
            self._last_play_ts = now
            self._play_count += 1
            if self._pan != 0.0 or self._pan_law == "constant_power":
                self._apply_pan()
            return True

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.channel = None
            self._paused = False
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
