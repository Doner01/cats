from pathlib import Path
from shutil import copytree, rmtree
from tempfile import TemporaryDirectory

PUBLIC_EXTENSIONS = {
    ".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".svg", ".png",
    ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif", ".webm", ".mp4",
}


def validate_assets(directory: Path) -> None:
    if directory.is_symlink():
        raise ValueError("Public asset directories must not be symbolic links")
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if path.is_symlink() or any(part.startswith(".") for part in relative.parts):
            raise ValueError(f"Unsafe public asset: {relative}")
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
        copytree(source, staged)
        public.mkdir(exist_ok=True)
        output = public / "static"
        if output.exists():
            rmtree(output)
        staged.replace(output)


if __name__ == "__main__":
    build_static(Path(__file__).resolve().parent)
