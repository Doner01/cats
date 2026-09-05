from pathlib import Path
from shutil import copytree, ignore_patterns
from tempfile import TemporaryDirectory

PUBLIC_EXTENSIONS = {
    ".css", ".js", ".map", ".json", ".txt", ".xml", ".webmanifest",
    ".woff", ".woff2", ".ttf", ".otf", ".svg", ".png",
    ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif", ".webm", ".mp4",
}


def validate_assets(directory: Path) -> None:
    if directory.is_symlink():
        raise ValueError("Public asset directories must not be symbolic links")
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if any(part.startswith(".") for part in relative.parts):
            continue  # silently skip dotfiles like .DS_Store, .gitkeep
        if path.is_symlink():
            raise ValueError(f"Unsafe public asset: {relative}")
        if not path.is_file() and not path.is_dir():
            raise ValueError(f"Unsupported public asset type: {relative}")
        if path.is_file() and path.suffix.lower() not in PUBLIC_EXTENSIONS:
            raise ValueError(f"Non-public file found in assets: {relative}")


def build_static(root: Path) -> None:
    source = root / "static"
    public = root / "public"
    if not source.is_dir():
        raise ValueError("The static asset directory is missing")
    validate_assets(source)
    if public.is_symlink():
        raise ValueError("The public directory must not be a symbolic link")
    if public.exists():
        if not public.is_dir():
            raise ValueError("The public output path must be a directory")
        if any(path.name != "static" for path in public.iterdir()):
            raise ValueError("Only generated static assets may be placed in public")
        validate_assets(public)
    # Validate and stage first, then replace only the generated asset directory.
    # A failed source validation must never damage the previous build.
    with TemporaryDirectory(prefix="catrank-assets-", dir=root) as temporary:
        staged = Path(temporary) / "static"
        # Validation skips hidden entries, so copying must skip them too. In
        # particular, nested .env files and .git directories must never reach
        # the public CDN even if their contents have an allowed extension.
        copytree(source, staged, ignore=ignore_patterns(".*"))
        validate_assets(staged)
        public.mkdir(exist_ok=True)
        output = public / "static"
        previous = Path(temporary) / "previous-static"
        if output.exists():
            output.replace(previous)
        try:
            staged.replace(output)
        except OSError:
            if previous.exists():
                previous.replace(output)
            raise


if __name__ == "__main__":
    build_static(Path(__file__).resolve().parent)
