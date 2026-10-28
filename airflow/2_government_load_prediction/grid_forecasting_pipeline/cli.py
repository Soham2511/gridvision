from __future__ import annotations

import argparse
import os
from pathlib import Path

from training.government_load.config import DATA_ROOT, PipelineSettings
from grid_forecasting_pipeline.etl import prepare_training_data
from training.government_load.modeling import predict, train_hybrid_model

DEFAULT_READY = DATA_ROOT / "training_ready_2018.parquet"
DEFAULT_PREDICTIONS = DATA_ROOT / "predictions_2018.parquet"


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", type=Path, help="Input parquet file")
    parser.add_argument("--features", type=Path, help="Saved joblib feature-column list")
    parser.add_argument("--memory-limit", help="DuckDB memory limit, for example 4GB")
    parser.add_argument("--threads", type=int, help="DuckDB and LightGBM thread count")
    parser.add_argument(
        "--max-training-rows",
        type=int,
        help="Maximum training rows to sample (default: 1000000)",
    )
    parser.add_argument(
        "--max-validation-rows",
        type=int,
        help="Maximum validation rows to sample (default: 250000)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grid-energy-pipeline",
        description="Prepare, train, and predict with the 2018 grid energy forecaster.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser("prepare", help="Build training-ready parquet")
    _add_common_options(prepare_parser)
    prepare_parser.add_argument("--output", type=Path, help="Training-ready parquet path")
    prepare_parser.add_argument("--horizon-hours", type=int, help="Maximum forecast horizon")

    train_parser = commands.add_parser("train", help="Fit and save the hybrid LightGBM model")
    _add_common_options(train_parser)
    train_parser.add_argument("--model-output", type=Path, help="Output joblib model path")
    train_parser.add_argument("--estimators", type=int, help="Number of trees per model")

    predict_parser = commands.add_parser("predict", help="Write predictions in parquet batches")
    _add_common_options(predict_parser)
    predict_parser.add_argument("--model", type=Path, help="Hybrid model joblib path")
    predict_parser.add_argument("--output", type=Path, help="Prediction parquet path")
    predict_parser.add_argument("--batch-size", type=int, help="Prediction rows per batch")

    run_parser = commands.add_parser("run", help="Prepare the dataset and train the model")
    _add_common_options(run_parser)
    run_parser.add_argument("--output", type=Path, help="Training-ready parquet path")
    run_parser.add_argument("--model-output", type=Path, help="Output joblib model path")
    run_parser.add_argument("--horizon-hours", type=int, help="Maximum forecast horizon")
    run_parser.add_argument("--estimators", type=int, help="Number of trees per model")
    return parser


def _settings_from_args(args: argparse.Namespace) -> PipelineSettings:
    settings = PipelineSettings.from_environment()
    values = settings.model_dump()

    if args.command in {"train", "predict"} and args.input is None:
        if "GOVERNMENT_PIPELINE_INPUT" not in os.environ:
            values["input_path"] = DEFAULT_READY
    if args.command == "run" and args.input is None:
        values["input_path"] = settings.input_path
    if (
        args.command == "predict"
        and args.output is None
        and "GOVERNMENT_PIPELINE_OUTPUT" not in os.environ
    ):
        values["output_path"] = DEFAULT_PREDICTIONS

    overrides = {
        "input_path": args.input,
        "feature_columns_path": args.features,
        "memory_limit": args.memory_limit,
        "threads": args.threads,
        "max_training_rows": args.max_training_rows,
        "max_validation_rows": args.max_validation_rows,
    }
    for field, value in overrides.items():
        if value is not None:
            values[field] = value

    if hasattr(args, "output") and args.output is not None:
        values["output_path"] = args.output
    if hasattr(args, "horizon_hours") and args.horizon_hours is not None:
        values["horizon_hours"] = args.horizon_hours
    if hasattr(args, "model_output") and args.model_output is not None:
        values["model_path"] = args.model_output
    if hasattr(args, "model") and args.model is not None:
        values["model_path"] = args.model
    if hasattr(args, "batch_size") and args.batch_size is not None:
        values["batch_size"] = args.batch_size
    if hasattr(args, "estimators") and args.estimators is not None:
        values["n_estimators"] = args.estimators
    return PipelineSettings(**values)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = _settings_from_args(args)

    if args.command in {"prepare", "run"}:
        ready_path = prepare_training_data(settings)
    else:
        ready_path = settings.input_path

    if args.command in {"train", "run"}:
        training_settings = PipelineSettings(
            **{
                **settings.model_dump(),
                "input_path": ready_path,
            }
        )
        train_hybrid_model(training_settings)
    elif args.command == "predict":
        predict(settings)


if __name__ == "__main__":
    main()
