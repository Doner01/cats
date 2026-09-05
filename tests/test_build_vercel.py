import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_vercel import build_static


class StaticBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "static"
        self.source.mkdir()
        (self.source / "app.js").write_text("new asset")

    def previous_build(self):
        output = self.root / "public" / "static"
        output.mkdir(parents=True)
        (output / "old.js").write_text("previous asset")
        return output

    def test_build_copies_assets_and_removes_stale_output(self):
        output = self.previous_build()
        build_static(self.root)
        self.assertEqual((output / "app.js").read_text(), "new asset")
        self.assertFalse((output / "old.js").exists())
        build_static(self.root)
        self.assertEqual((output / "app.js").read_text(), "new asset")

    def test_hidden_files_and_directories_never_reach_public(self):
        (self.source / ".env").write_text("PRIVATE_FIXTURE")
        nested = self.source / "images"
        nested.mkdir()
        (nested / ".env.production").write_text("PRIVATE_FIXTURE")
        (nested / ".config").mkdir()
        (nested / ".config" / "credentials.json").write_text("PRIVATE_FIXTURE")
        build_static(self.root)
        output = self.root / "public" / "static"
        self.assertFalse(any(part.startswith(".") for path in output.rglob("*") for part in path.relative_to(output).parts))
        self.assertTrue((output / "app.js").is_file())

    def test_disallowed_source_preserves_previous_build(self):
        output = self.previous_build()
        (self.source / "private.pem").write_text("PRIVATE_FIXTURE")
        with self.assertRaisesRegex(ValueError, "Non-public"):
            build_static(self.root)
        self.assertEqual((output / "old.js").read_text(), "previous asset")

    def test_visible_symlinks_are_rejected(self):
        (self.source / "linked.js").symlink_to(self.source / "app.js")
        with self.assertRaisesRegex(ValueError, "Unsafe public asset"):
            build_static(self.root)

    def test_hidden_symlink_is_excluded(self):
        private = self.root / "private"
        private.mkdir()
        (private / "secret.json").write_text("PRIVATE_FIXTURE")
        (self.source / ".private").symlink_to(private, target_is_directory=True)
        build_static(self.root)
        self.assertFalse((self.root / "public" / "static" / ".private").exists())

    def test_public_symlink_is_rejected(self):
        (self.root / "public").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "public directory"):
            build_static(self.root)

    def test_source_directory_symlink_is_rejected(self):
        self.source.rename(self.root / "assets")
        self.source.symlink_to(self.root / "assets", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            build_static(self.root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_special_files_are_rejected_before_copying(self):
        os.mkfifo(self.source / "stream.js")
        with self.assertRaisesRegex(ValueError, "Unsupported public asset type"):
            build_static(self.root)

    def test_failed_publish_restores_previous_build(self):
        output = self.previous_build()
        replace = Path.replace

        def failing_replace(path, target):
            if path.name == "static" and path.parent.name.startswith("catrank-assets-"):
                raise OSError("simulated publish failure")
            return replace(path, target)

        with patch.object(Path, "replace", failing_replace):
            with self.assertRaisesRegex(OSError, "simulated publish failure"):
                build_static(self.root)
        self.assertEqual((output / "old.js").read_text(), "previous asset")
        self.assertEqual(list(self.root.glob("catrank-assets-*")), [])

    def test_unmanaged_public_files_are_preserved_and_rejected(self):
        self.previous_build()
        private = self.root / "public" / "private.txt"
        private.write_text("PRIVATE_FIXTURE")
        with self.assertRaisesRegex(ValueError, "Only generated"):
            build_static(self.root)
        self.assertEqual(private.read_text(), "PRIVATE_FIXTURE")


if __name__ == "__main__":
    unittest.main()
