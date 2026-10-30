from pathlib import Path
import re

spec = Path("buildozer.spec")
if not spec.exists():
    raise SystemExit("buildozer.spec was not generated")

text = spec.read_text(encoding="utf-8")
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

spec.write_text(text, encoding="utf-8")
