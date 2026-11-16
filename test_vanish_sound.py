import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from vanish_sound import VanishSound, SOUND_PATH


class TestVanishSound(unittest.TestCase):
    def test_sound_asset_exists(self):
        self.assertTrue(SOUND_PATH.is_file(), f"Asset sound must exist at {SOUND_PATH}")

    def test_missing_file_raises_runtime_error(self):
        bogus_path = Path("non_existent_file.mp3")
        with self.assertRaises(RuntimeError) as ctx:
            VanishSound(bogus_path)
        self.assertIn("non trovato", str(ctx.exception))

    def test_ffplay_path_mocked(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            
            vs = VanishSound(SOUND_PATH)
            self.assertEqual(vs.ffplay, "/usr/bin/ffplay")

            # Play triggers subprocess
            vs.play()
            mock_popen.assert_called_once()
            self.assertIs(vs.process, mock_process)

            # Close terminates, waits, and clears handle (idempotent)
            vs.close()
            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once()
            self.assertIsNone(vs.process)
            vs.close()
            mock_process.terminate.assert_called_once()

    def test_terminate_process_lookup_error_handled(self):
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.terminate.side_effect = ProcessLookupError("Process already exited")

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}):
            
            vs = VanishSound(SOUND_PATH)
            vs.process = mock_process
            # Closing when process already exited should not raise and clears process
            vs.close()
            self.assertIsNone(vs.process)

    def test_hung_ffplay_escalates_to_kill_on_timeout(self):
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("ffplay", 2.0), None]

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}):
            vs = VanishSound(SOUND_PATH)
            vs.process = mock_process
            vs.close()

            mock_process.terminate.assert_called_once()
            mock_process.kill.assert_called_once()
            self.assertIsNone(vs.process)

    def test_context_manager_cleans_up_on_exception(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process):
            with self.assertRaises(ValueError):
                with VanishSound(SOUND_PATH) as vs:
                    vs.play()
                    raise ValueError("simulated crash")

            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once()

    def test_string_path_accepted_and_post_close_play_rejected(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process):
            vs = VanishSound(str(SOUND_PATH))
            self.assertEqual(vs.path, SOUND_PATH)
            vs.close()
            with self.assertRaises(RuntimeError):
                vs.play()

    def test_non_mp3_missing_file_does_not_fallback_to_mp3(self):
        with self.assertRaises(RuntimeError) as ctx:
            VanishSound(Path("non_existent_audio.wav"))
        self.assertIn("non trovato", str(ctx.exception))

    def test_default_and_none_path_defaults_to_sound_path(self):
        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}):
            vs_none = VanishSound(None)
            self.assertEqual(vs_none.path, SOUND_PATH)
            vs_empty = VanishSound("")
            self.assertEqual(vs_empty.path, SOUND_PATH)

    def test_destructor_closes_child_process(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process):
            vs = VanishSound()
            vs.play()
            vs.__del__()
            mock_process.terminate.assert_called_once()

    def test_volume_clamping_and_ffplay_flags(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            # Volume bounds and guards
            vs = VanishSound(volume=1.5)
            self.assertEqual(vs.volume, 1.0)
            vs.set_volume(-0.5)
            self.assertEqual(vs.volume, 0.0)
            vs.set_volume(float("nan"))
            self.assertEqual(vs.volume, 1.0)
            vs.set_volume(True)
            self.assertEqual(vs.volume, 1.0)

            # Volume < 1.0 passes -volume to ffplay
            vs.set_volume(0.6)
            vs.play()
            called_args = mock_popen.call_args[0][0]
            self.assertIn("-volume", called_args)
            self.assertIn("60", called_args)

    def test_stop_and_is_playing_lifecycle(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process):
            vs = VanishSound()
            self.assertFalse(vs.is_playing())

            vs.play()
            self.assertTrue(vs.is_playing())

            vs.stop()
            self.assertFalse(vs.is_playing())
            mock_process.terminate.assert_called_once()

    def test_fade_out_and_is_closed_properties(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process):
            vs = VanishSound(volume=0.85)
            self.assertFalse(vs.is_closed)
            self.assertAlmostEqual(vs.get_volume(), 0.85)

            vs.play()
            vs.fade_out(duration_ms=400)
            mock_process.terminate.assert_called_once()

            vs.close()
            self.assertTrue(vs.is_closed)

    def test_play_loops_ffplay_arguments(self):
        mock_process = Mock()
        mock_process.poll.return_value = None

        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch.dict("sys.modules", {"pygame": None, "pygame.mixer": None}), \
             patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            vs = VanishSound()

            # loops = 2 -> -loop 3
            vs.play(loops=2)
            called_args = mock_popen.call_args[0][0]
            self.assertIn("-loop", called_args)
            self.assertIn("3", called_args)

            # loops = -1 -> -loop 0 (infinite)
            vs.play(loops=-1)
            called_args = mock_popen.call_args[0][0]
            self.assertIn("-loop", called_args)
            self.assertIn("0", called_args)

    def test_pygame_fadeout_and_loop_calls(self):
        mock_mixer = Mock()
        mock_mixer.get_init.return_value = True
        mock_sound = Mock()
        mock_mixer.Sound.return_value = mock_sound
        mock_pygame = Mock(mixer=mock_mixer)

        with patch.dict("sys.modules", {"pygame": mock_pygame, "pygame.mixer": mock_mixer}):
            vs = VanishSound()
            vs.play(loops=3)
            mock_sound.play.assert_called_with(loops=3)

            vs.fade_out(500)
            mock_sound.fadeout.assert_called_with(500)

    def test_mute_unmute_and_length_introspection(self):
        mock_mixer = Mock()
        mock_mixer.get_init.return_value = True
        mock_sound = Mock()
        mock_sound.get_length.return_value = 1.45
        mock_mixer.Sound.return_value = mock_sound
        mock_pygame = Mock(mixer=mock_mixer)

        with patch.dict("sys.modules", {"pygame": mock_pygame, "pygame.mixer": mock_mixer}):
            vs = VanishSound(volume=0.8)
            self.assertEqual(vs.get_volume(), 0.8)
            self.assertFalse(vs.is_muted)
            self.assertEqual(vs.get_length(), 1.45)

            vs.mute()
            self.assertEqual(vs.get_volume(), 0.0)
            self.assertTrue(vs.is_muted)

            vs.unmute()
            self.assertEqual(vs.get_volume(), 0.8)
            self.assertFalse(vs.is_muted)

    def test_pause_unpause_and_panning_controls(self):
        mock_mixer = Mock()
        mock_mixer.get_init.return_value = True
        mock_channel = Mock()
        mock_sound = Mock()
        mock_sound.play.return_value = mock_channel
        mock_mixer.Sound.return_value = mock_sound
        mock_pygame = Mock(mixer=mock_mixer)

        with patch.dict("sys.modules", {"pygame": mock_pygame, "pygame.mixer": mock_mixer}):
            vs = VanishSound(volume=0.8)
            self.assertFalse(vs.is_paused)
            self.assertEqual(vs.get_pan(), 0.0)

            vs.play()
            self.assertIs(vs.channel, mock_channel)

            vs.pause()
            mock_channel.pause.assert_called_once()
            self.assertTrue(vs.is_paused)

            vs.unpause()
            mock_channel.unpause.assert_called_once()
            self.assertFalse(vs.is_paused)

            # Test stereo panning
            vs.set_pan(0.5)
            self.assertEqual(vs.get_pan(), 0.5)
            # Left: (1.0 - 0.5) * 0.8 = 0.4, Right: (1.0) clamped * 0.8 = 0.8
            mock_channel.set_volume.assert_called_with(0.4, 0.8)

            # Test clamping
            vs.set_pan(-2.0)
            self.assertEqual(vs.get_pan(), -1.0)
            vs.set_pan(float("nan"))
            self.assertEqual(vs.get_pan(), 0.0)

            vs.stop()
            self.assertIsNone(vs.channel)
            self.assertFalse(vs.is_paused)



if __name__ == "__main__":
    unittest.main()
