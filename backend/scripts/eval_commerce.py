"""Run the vendored commerce evaluations against B-agent's buyer assistant.

    python scripts/eval_commerce.py go-live                 # offline retrieval baseline
    python scripts/eval_commerce.py go-live --mode live --failures
    python scripts/eval_commerce.py constraints
    python scripts/eval_commerce.py constraints --mode live

``go-live`` scores trade-terms answers on correct, traceable, version-valid and safe;
``constraints`` reports the Constraint Violation Rate of recommended products. Both are
``commerce/scripts/eval_go_live.py`` and ``eval_constraints.py`` unchanged, with a
``bagent`` vertical (``app.commerce.evaluation.EvalStorefront`` over the demo catalog) and
the foreign-trade cases in ``scripts/commerce_eval_cases/``. Live mode calls the model the
commerce runtime resolves from B-agent's AI settings (``app.commerce.runtime``).
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
COMMERCE = BACKEND.parent / "commerce"
CASES = BACKEND / "scripts" / "commerce_eval_cases"
sys.path[:0] = [str(BACKEND), str(COMMERCE / "scripts"), str(COMMERCE / "examples")]

import eval_constraints  # noqa: E402
import eval_go_live  # noqa: E402

from app.commerce.runtime import resolve_model, shopping_config  # noqa: E402


def agent_setup(vertical: str, mode: str):
    del vertical
    choice = resolve_model()
    config = shopping_config(choice)
    if mode != "live":
        return None, config
    if not choice.configured:
        raise SystemExit(
            "--mode live: no model is configured for the commerce assistants "
            "(COMMERCE_MODEL_* or the AI runtime settings)."
        )
    return choice.client, config


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("go-live", "constraints"):
        print(__doc__)
        return 2
    command, rest = sys.argv[1], sys.argv[2:]
    eval_go_live.VERTICALS["bagent"] = eval_go_live.Vertical("app.commerce.evaluation:EvalStorefront")
    eval_go_live.agent_setup = agent_setup
    eval_constraints.agent_setup = agent_setup
    eval_go_live.CASES_DIR = CASES / "go_live"
    eval_constraints.CASES_DIR = CASES / "constraints"
    module = eval_go_live if command == "go-live" else eval_constraints
    sys.argv = [f"eval_commerce.py {command}", "--vertical", "bagent", *rest]
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
