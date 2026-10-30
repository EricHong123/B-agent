import subprocess
import sys
from pathlib import Path

import pytest

from app.commerce.evaluation import EvalStorefront


BACKEND = Path(__file__).resolve().parents[1]


def run_eval(command, tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/eval_commerce.py", command],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PATH": "", "DATABASE_URL": f"sqlite:///{tmp_path / 'eval.db'}", "PYTHONPATH": str(BACKEND)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_offline_go_live_baseline_holds_every_non_handoff_case(tmp_path):
    output = run_eval("go-live", tmp_path)
    assert "surface accuracy  25/25" in output
    assert "go-live rate      23/25" in output


def test_offline_constraint_baseline_shows_no_unmarked_violation(tmp_path):
    output = run_eval("constraints", tmp_path)
    assert "Constraint Violation Rate  0/10" in output


@pytest.mark.parametrize("variant", ["BTL-5001-BLK", "BTL-5001-SGE"])
def test_variants_inherit_family_trade_attributes(variant):
    product = EvalStorefront().product(variant)
    assert product.attributes["material"] == "18/8 stainless steel"
    assert product.attributes["port_of_loading"] == "Ningbo"
    assert product.attributes["moq"] == "500 pcs"


def test_made_to_order_products_stay_orderable():
    product = EvalStorefront().product("BAG-7012")
    assert product.in_stock is True
    assert product.attributes["availability"] == "made to order, 28 days"
