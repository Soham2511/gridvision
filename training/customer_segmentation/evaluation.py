"""Multi-criteria clustering evaluation and stability diagnostics."""

from __future__ import annotations

from itertools import combinations
from math import ceil
from typing import Any

import numpy as np
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)


def _fit_candidate(kind: str, k: int, seed: int, x: np.ndarray):
    if kind == "kmeans":
        from sklearn.cluster import KMeans

        model = KMeans(n_clusters=k, n_init=10, random_state=seed, algorithm="lloyd")
        model.fit(x)
        return model, model.labels_
    if kind == "gmm":
        from sklearn.mixture import GaussianMixture

        model = GaussianMixture(
            n_components=k,
            covariance_type="full",
            reg_covar=1e-6,
            n_init=2,
            random_state=seed,
        )
        model.fit(x)
        return model, model.predict(x)
    raise ValueError(f"Unsupported clustering algorithm: {kind}")


def _metric_scores(x: np.ndarray, labels: np.ndarray, seed: int) -> dict[str, float]:
    unique, counts = np.unique(labels, return_counts=True)
    if len(unique) < 2 or len(unique) >= len(labels):
        raise ValueError("Degenerate clustering produced fewer than 2 or too many clusters")
    sample_size = min(5000, len(labels))
    silhouette = silhouette_score(
        x,
        labels,
        sample_size=sample_size if sample_size < len(labels) else None,
        random_state=seed,
    )
    return {
        "silhouette": float(silhouette),
        "davies_bouldin": float(davies_bouldin_score(x, labels)),
        "calinski_harabasz": float(calinski_harabasz_score(x, labels)),
        "smallest_cluster_size": int(counts.min()),
        "largest_cluster_size": int(counts.max()),
        "cluster_count": int(len(unique)),
        "cluster_size_distribution": {
            str(int(cluster)): int(size)
            for cluster, size in zip(unique, counts)
        },
        "silhouette_sample_size": int(sample_size),
    }


def _stability(kind: str, k: int, x: np.ndarray, seed: int) -> float:
    label_runs = [
        _fit_candidate(kind, k, seed + offset, x)[1]
        for offset in (0, 17, 37)
    ]
    agreements = [
        adjusted_rand_score(label_runs[left], label_runs[right])
        for left, right in combinations(range(len(label_runs)), 2)
    ]
    return float(np.mean(agreements))


def _selection_ranks(candidates: list[dict[str, Any]]) -> None:
    """Attach equal-weight mean ranks across quality, stability and balance measures."""
    metrics = (
        ("silhouette", True),
        ("davies_bouldin", False),
        ("calinski_harabasz", True),
        ("stability_ari", True),
        ("smallest_cluster_share", True),
    )
    for candidate in candidates:
        candidate["selection_rank_components"] = {}
    for metric, higher_is_better in metrics:
        ordered = sorted(
            candidates,
            key=lambda item: item[metric],
            reverse=higher_is_better,
        )
        for rank, candidate in enumerate(ordered, start=1):
            candidate["selection_rank_components"][metric] = rank
    for candidate in candidates:
        candidate["mean_selection_rank"] = float(
            np.mean(list(candidate["selection_rank_components"].values()))
        )


def evaluate_candidates(
    x: np.ndarray,
    *,
    min_k: int,
    max_k: int,
    seed: int,
    include_hdbscan: bool = True,
    minimum_cluster_size: int = 5,
    minimum_cluster_fraction: float = 0.005,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Compare available models without selecting on a single metric."""
    if x.ndim != 2 or x.shape[0] < 4 or x.shape[1] < 1:
        raise ValueError("Clustering requires at least 4 rows and 1 usable feature")
    max_supported_k = min(max_k, x.shape[0] - 1)
    required_cluster_size = max(minimum_cluster_size, ceil(len(x) * minimum_cluster_fraction))
    candidates: list[dict[str, Any]] = []
    for algorithm in ("kmeans", "gmm"):
        for k in range(min_k, max_supported_k + 1):
            try:
                model, labels = _fit_candidate(algorithm, k, seed, x)
                scores = _metric_scores(x, labels, seed)
                if scores["smallest_cluster_size"] < required_cluster_size:
                    candidates.append(
                        {
                            "algorithm": algorithm,
                            "k": k,
                            "valid": False,
                            "reason": (
                                f"smallest cluster has {scores['smallest_cluster_size']} buildings; "
                                f"minimum is {required_cluster_size}"
                            ),
                            **scores,
                        }
                    )
                    continue
                scores["stability_ari"] = _stability(algorithm, k, x, seed)
                scores["smallest_cluster_share"] = scores["smallest_cluster_size"] / len(x)
                candidates.append(
                    {
                        "algorithm": algorithm,
                        "k": k,
                        "valid": True,
                        "model": model,
                        "labels": labels,
                        **scores,
                    }
                )
            except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
                candidates.append(
                    {"algorithm": algorithm, "k": k, "valid": False, "reason": str(exc)}
                )
    hdbscan_status: dict[str, Any]
    if include_hdbscan:
        try:
            from hdbscan import HDBSCAN
        except ImportError as exc:
            hdbscan_status = {"available": False, "reason": str(exc)}
        else:
            # Restrict candidate fitting to supported dataset sizes; callers can opt out
            # when the full clustering cannot fit within their scale/memory budget.
            if len(x) <= 100_000:
                model = HDBSCAN(min_cluster_size=max(5, min(50, len(x) // 20)))
                labels = model.fit_predict(x)
                valid_labels = labels >= 0
                if valid_labels.sum() >= 4 and len(np.unique(labels[valid_labels])) >= 2:
                    scores = _metric_scores(x[valid_labels], labels[valid_labels], seed)
                    scores["stability_ari"] = float("nan")
                    scores["smallest_cluster_share"] = scores["smallest_cluster_size"] / len(x)
                    scores["outlier_share"] = float((~valid_labels).mean())
                    if scores["smallest_cluster_size"] < required_cluster_size:
                        candidates.append(
                            {
                                "algorithm": "hdbscan",
                                "k": scores["cluster_count"],
                                "valid": False,
                                "reason": f"smallest cluster below required size {required_cluster_size}",
                                **scores,
                            }
                        )
                    else:
                        candidates.append(
                            {
                                "algorithm": "hdbscan",
                                "k": scores["cluster_count"],
                                "valid": True,
                                "model": model,
                                "labels": labels,
                                **scores,
                            }
                        )
                hdbscan_status = {
                    "available": True,
                    "evaluated": len(x) <= 100_000,
                    "reason": None if len(x) <= 100_000 else "dataset exceeds 100000-row evaluation limit",
                }
    else:
        hdbscan_status = {"available": False, "reason": "disabled by caller"}
    valid = [item for item in candidates if item.get("model") is not None]
    # HDBSCAN is included for diagnostics when installed, but its inference and
    # stability contract differs from the assignable K-Means/GMM candidates.
    rankable = [
        item
        for item in valid
        if item.get("algorithm") in {"kmeans", "gmm"}
        and np.isfinite(item.get("stability_ari", np.nan))
    ]
    if rankable:
        _selection_ranks(rankable)
    selected = (
        min(rankable or valid, key=lambda item: item.get("mean_selection_rank", float("inf")))
        if rankable
        else None
    )
    report_candidates = []
    for item in candidates:
        report_candidates.append(
            {key: value for key, value in item.items() if key not in {"model", "labels"}}
        )
    selected_summary = (
        {key: value for key, value in selected.items() if key not in {"model", "labels"}}
        if selected
        else None
    )
    return selected, {
        "selection_method": (
            "lowest mean rank across silhouette, Davies-Bouldin, Calinski-Harabasz, "
            "seed stability (adjusted Rand), and smallest-cluster share"
        ),
        "hdbscan": hdbscan_status,
        "required_cluster_size": required_cluster_size,
        "selected": selected_summary,
        "candidates": report_candidates,
    }

