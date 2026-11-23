from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .config import Config, ConfigError, load_config
from .experiment import ExperimentError, Stimulus, check_wav, load_manifest, load_trial_list


def validate(config: Config) -> dict[str, Stimulus]:
    stimuli = load_manifest(config.manifest, config.sample_rate)
    if config.volume_reference is not None:
        check_wav(config.volume_reference, config.sample_rate, "volume_reference")
    if not config.trial_lists.is_dir():
        raise ExperimentError(f"trial_lists folder not found: {config.trial_lists}")
    lists = sorted(config.trial_lists.glob("*.csv"))
    if not lists:
        raise ExperimentError(f"no trial lists (*.csv) in {config.trial_lists}")
    for p in lists:
        load_trial_list(p, stimuli)
    print(f"config       {config.path}")
    print(f"manifest     {len(stimuli)} stimuli, all {config.sample_rate} Hz stereo")
    print(f"trial lists  {len(lists)} in {config.trial_lists}")
    print(f"results  ->  {config.results}")
    print(f"response     {config.response.mode}, externalization {config.response.externalization}, "
          f"max_replays {config.max_replays}")
    return stimuli


def run_design(config: Config, force: bool) -> None:
    from .design import parse_design, write_trial_lists

    design = parse_design(config.design)  # type: ignore[arg-type]
    stimuli = load_manifest(config.manifest, config.sample_rate)
    report = write_trial_lists(design, stimuli, config.trial_lists, overwrite=force)
    for kind, paths in report.items():
        if paths:
            print(f"{kind:<12}{len(paths):>4}  {', '.join(p.stem for p in paths)}")
    print(f"trial lists in {config.trial_lists}")


def run_analyze(config: Config, args: argparse.Namespace) -> None:
    from .analysis import merge, summarize

    trials = merge(config.results, config.manifest,
                   include_training=args.include_training, include_catch=args.include_catch)
    by = [c.strip() for c in args.by.split(",") if c.strip()]
    missing = [c for c in by if c not in trials.columns]
    if missing:
        raise ValueError(f"--by column(s) not found: {missing}")
    out = args.out or (config.results / "analysis")
    out.mkdir(parents=True, exist_ok=True)
    trials.to_csv(out / "trials.csv", index=False)
    summarize(trials, by=by).to_csv(out / "summary.csv", index=False)
    print(f"{len(trials)} trials from {trials['participant_id'].nunique()} participant(s)")
    print(f"wrote {out / 'trials.csv'}")
    print(f"wrote {out / 'summary.csv'}  (grouped by {', '.join(by)})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="binaural_loc", description="Binaural localization listening tests")
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        "serve": "run the experiment server",
        "check": "validate config, manifest, trial lists and audio",
        "design": "generate trial lists",
        "analyze": "merge results and compute errors",
    }
    for name, help_ in commands.items():
        p = sub.add_parser(name, help=help_)
        p.add_argument("--config", required=True, type=Path, help="experiment YAML")
        if name == "serve":
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=8000)
            p.add_argument("--open", action="store_true", help="open the browser")
        if name == "design":
            p.add_argument("--force", action="store_true", help="overwrite trial lists that would change")
        if name == "analyze":
            p.add_argument("--by", default="participant_id",
                           help="comma-separated grouping columns for the summary (e.g. participant_id,condition)")
            p.add_argument("--out", type=Path, help="output folder (default: <results>/analysis)")
            p.add_argument("--include-training", action="store_true")
            p.add_argument("--include-catch", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        if args.command == "design":
            return run_design(config, args.force)
        if args.command == "analyze":
            return run_analyze(config, args)
        stimuli = validate(config)
    except (ConfigError, ExperimentError, OSError, ValueError) as e:
        sys.exit(f"error: {e}")

    if args.command == "check":
        print("OK")
        return

    import uvicorn

    from .server.app import WEB_DIST, create_app

    if not (WEB_DIST / "index.html").is_file():
        sys.exit(f"error: front end not built ({WEB_DIST} missing). Run once:\n  npm --prefix binaural_loc/web install\n"
                 f"  npm --prefix binaural_loc/web run build")
    url = f"http://{args.host}:{args.port}/"
    print(f"\nopen {url}  (Ctrl+C to stop)\n", flush=True)
    if args.open:
        webbrowser.open(url)
    uvicorn.run(create_app(config, stimuli), host=args.host, port=args.port, log_level="warning")
