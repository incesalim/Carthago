"""Gate explicit publishing scopes, shared writer queues and snapshot ownership."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def boundary_errors(text: str) -> list[str]:
    """Snapshot/analyst publication rules that must hold in workflows and code."""
    errors = []
    if re.search(r"upload_file\([^\n]*[\"']state/(bddk_data|bank_audit|analyst)\.db\.gz", text):
        errors.append("authoritative snapshots must use publish_snapshot")
    if re.search(r"name: Upload analyst staging state to R2\n\s+if: always\(\)", text):
        errors.append("failed analyst publication must not promote the current snapshot")
    return errors


def workflow_errors(text: str) -> list[str]:
    errors = []
    for step in re.split(r"\n      - ", text):
        if re.search(r"python\s+scripts/push_to_d1\.py", step):
            if not re.search(r"--(?:table-set|only-tables)\b", step):
                errors.append("publisher call has no explicit table scope")
    for block in re.findall(r"(?m)^([ \t]*)concurrency:\n((?:(?:\1[ \t]+.*|[ \t]*)\n)+)", text):
        body = block[1]
        if re.search(r"group:\s*(bddk-pipeline|bddk-audit|carthago-production-release)\s*\n", body):
            if "queue: max" not in body or "cancel-in-progress: false" not in body:
                errors.append("shared writer lock must retain pending runs and never cancel the writer")
    return errors + boundary_errors(text)


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        errors.extend(f"{path.name}: {e}" for e in workflow_errors(text))
        if path.name != "deploy-cloudflare.yml" and re.search(
                r"wrangler[^\n]*d1[^\n]*(?:migrations apply|--file[= ](?:web/)?migrations/)", text):
            errors.append(f"{path.name}: ingestion must not apply serving DDL")
    for path in sorted(list((root / "scripts").rglob("*.py")) + list((root / "src").rglob("*.py"))):
        if "archive" in path.parts:
            continue  # Archived tools are outside the supported publication surface.
        text = path.read_text(encoding="utf-8")
        errors.extend(f"{path.name}: {e}" for e in boundary_errors(text))
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.List):
                continue
            strings = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if "push_to_d1.py" in strings and not any(value.split("=")[0] in {"--table-set", "--only-tables"} for value in strings):
                errors.append(f"{path.name}:{node.lineno}: publisher command has no explicit scope")
    return errors


if __name__ == "__main__":
    errors = check()
    print("\n".join(errors) if errors else "Publication scopes, queues and snapshot routes pass")
    raise SystemExit(bool(errors))
