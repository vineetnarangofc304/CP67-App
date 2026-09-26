"""Point 51 (Sep 2026): tapping Reprocess must HIT FUNDLE ONLY — never
silently force-credit. Regression guard: parses server.py directly so the
test doesn't need to import the full FastAPI app (which pulls sibling
`routes.consumer` and has env-time dependencies)."""
import re
from pathlib import Path

SERVER_PY = Path(__file__).parent.parent / "server.py"
SRC = SERVER_PY.read_text()


def _extract_fn(src: str, name: str) -> str:
    """Return the source text of a top-level async def block (including
    blank lines inside the body)."""
    m = re.search(
        rf"^async def {name}\(.*?(?=^(?:async def|def|class)\s)",
        src,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert m, f"function {name} not found"
    return m.group(0)


def test_bg_reprocess_never_force_credits():
    fn = _extract_fn(SRC, "_do_reprocess_bill_bg")
    m = re.search(r"force_credit_on_fundle_reject\s*=\s*(True|False)", fn)
    assert m is not None, "flag must be explicit"
    assert m.group(1) == "False", (
        f"Point 51: _do_reprocess_bill_bg must pass False, got {m.group(1)}"
    )


def test_sync_reprocess_never_force_credits():
    fn = _extract_fn(SRC, "_do_reprocess_bill_sync")
    m = re.search(r"force_credit_on_fundle_reject\s*=\s*(True|False)", fn)
    assert m is not None
    assert m.group(1) == "False", (
        f"Point 51: _do_reprocess_bill_sync must pass False, got {m.group(1)}"
    )


def test_bulk_reprocess_model_default_still_false():
    """Regression: the BulkReprocessRequest default must stay False so
    admin still explicitly opts in on the bulk modal."""
    m = re.search(
        r"class BulkReprocessRequest\(BaseModel\).*?force_credit_on_fundle_reject:\s*bool\s*=\s*(True|False)",
        SRC, re.DOTALL,
    )
    assert m is not None, "BulkReprocessRequest.force_credit_on_fundle_reject default not found"
    assert m.group(1) == "False"


def test_edit_brand_model_default_still_false():
    """Regression: Point 49 fix — EditBrandRequest keeps auto_force_credit off."""
    m = re.search(
        r"class EditBrandRequest\(BaseModel\).*?auto_force_credit_on_fundle_reject:\s*bool\s*=\s*(True|False)",
        SRC, re.DOTALL,
    )
    assert m is not None
    assert m.group(1) == "False"

