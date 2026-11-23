"""Build and run the demo.

    python examples/demo/run.py              run it in the browser
    python examples/demo/run.py --simulate   simulated listeners and analysis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "experiment.yaml"
sys.path.insert(0, str(HERE))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulate", action="store_true", help="simulated listeners and analysis")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from binaural_loc.cli import main as cli

    if not (HERE / "stimuli" / "manifest.csv").is_file():
        import make_demo

        make_demo.main()
    cli(["design", "--config", str(CONFIG)])

    if args.simulate:
        from simulate_listeners import simulate

        cli(["check", "--config", str(CONFIG)])
        simulate(CONFIG, ["P01", "P02", "P03", "P04"])
        cli(["analyze", "--config", str(CONFIG), "--by", "condition"])
        print("\nOpen examples/demo/results/analysis/summary.csv (or trials.csv) to see the results.")
    else:
        print("\nParticipant IDs: P01-P04, any session ID (e.g. S1).\n")
        cli(["serve", "--config", str(CONFIG), "--port", str(args.port), "--open"])


if __name__ == "__main__":
    main()
