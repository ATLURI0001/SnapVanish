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

            # Close terminates subprocess
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
            # Closing when process already exited should not raise
            vs.close()


if __name__ == "__main__":
    unittest.main()
