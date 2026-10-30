from pathlib import Path
import os
import re

spec = Path("buildozer.spec")
if not spec.exists():
    raise SystemExit("buildozer.spec was not generated")

text = spec.read_text(encoding="utf-8")


def set_app_option(name: str, value: str) -> None:
    global text
    pattern = re.compile(rf"(?m)^{re.escape(name)}\s*=.*$")
    if pattern.search(text):
        text = pattern.sub(f"{name} = {value}", text, count=1)
        return

    app_section = re.search(r"(?m)^\[app\]\s*$", text)
    if not app_section:
        raise SystemExit("[app] section missing from buildozer.spec")
    insert_at = app_section.end()
    text = text[:insert_at] + f"\n{name} = {value}" + text[insert_at:]


match = re.search(r"(?m)^android\.permissions\s*=\s*(.*)$", text)
if match:
    existing = [item.strip() for item in match.group(1).split(",") if item.strip()]
    if "INTERNET" not in existing:
        existing.append("INTERNET")
        text = text[:match.start(1)] + ", ".join(existing) + text[match.end(1):]
else:
    app_section = re.search(r"(?m)^\[app\]\s*$", text)
    if not app_section:
        raise SystemExit("[app] section missing from buildozer.spec")
    insert_at = app_section.end()
    text = text[:insert_at] + "\nandroid.permissions = INTERNET" + text[insert_at:]

# Build a directly installable APK and give every workflow attempt a newer
# Android versionCode so it can update an already-installed release.
set_app_option("android.release_artifact", "apk")
run_number = os.environ.get("GITHUB_RUN_NUMBER")
run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
if run_number:
    version_code = int(run_number) * 100 + int(run_attempt)
    if not 1 <= version_code <= 2_100_000_000:
        raise SystemExit(f"Android versionCode is out of range: {version_code}")
    set_app_option("android.numeric_version", str(version_code))

spec.write_text(text, encoding="utf-8")
