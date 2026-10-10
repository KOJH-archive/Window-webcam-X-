from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".cmd", ".vbs"}
SKIP_PARTS = {".venv", ".git", ".pytest_cache", ".uv-cache", "__pycache__", ".pytest_tmp"}


def test_public_tree_has_no_machine_or_user_identifiers():
    forbidden = (
        "LG" + " Gram",
        "16" + "Z90",
        "LGE" + " Camera",
        "jon" + "gh",
        "C:" + "\\Users\\",
    )
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts) or path.name == "config.local.yaml":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for value in forbidden:
            if value.lower() in text.lower():
                findings.append(f"{path.relative_to(ROOT)}: {value}")
    assert not findings, "private identifiers found:\n" + "\n".join(findings)


def test_local_and_measurement_outputs_are_gitignored():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in ("config.local.yaml", "*.db", "*.csv", "*.log", "baseline.json"):
        assert rule in rules
    assert not (ROOT / "IMPLEMENTATION_REPORT.md").exists()
