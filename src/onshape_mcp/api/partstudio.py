"""Part Studio feature endpoints: list/add features, FeatureScript eval.

Every modeling operation returns the compact {featureId, name, featureStatus}
shape — featureStatus (OK | WARNING | ERROR) is the regen-error feedback loop.
"""

from __future__ import annotations

from typing import Any

from ..client import OnshapeClient
from ..queries import unwrap_fs_value

FEATURE_CALL_BTTYPE = "BTFeatureDefinitionCall-1406"


def _feature_summary(feature: dict[str, Any], status: str | None) -> dict[str, Any]:
    return {
        "featureId": feature.get("featureId"),
        "name": feature.get("name"),
        "featureType": feature.get("featureType"),
        "featureStatus": status,
    }


def get_features(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str | None = None,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    params = {"featureId": feature_id} if feature_id else None
    data = client.request_json(
        "GET",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features",
        params=params,
    )
    states = data.get("featureStates", {})
    results = []
    for feature in data.get("features", []):
        fid = feature.get("featureId")
        status = (states.get(fid) or {}).get("featureStatus")
        summary = _feature_summary(feature, status)
        if verbose:
            summary["feature"] = feature
        results.append(summary)
    return results


def add_feature(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature: dict[str, Any],
) -> dict[str, Any]:
    """POST one feature. Accepts either a bare feature dict (BTMSketch-151,
    BTMFeature-134, ...) or a full BTFeatureDefinitionCall-1406 envelope."""
    if feature.get("btType") != FEATURE_CALL_BTTYPE:
        feature = {"btType": FEATURE_CALL_BTTYPE, "feature": feature}
    data = client.request_json(
        "POST",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features",
        json_body=feature,
    )
    returned = data.get("feature", {})
    status = (data.get("featureState") or {}).get("featureStatus")
    return _feature_summary(returned, status)


def update_feature(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
    feature: dict[str, Any],
) -> dict[str, Any]:
    if feature.get("btType") != FEATURE_CALL_BTTYPE:
        feature = {"btType": FEATURE_CALL_BTTYPE, "feature": feature}
    data = client.request_json(
        "POST",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}"
        f"/features/featureid/{feature_id}",
        json_body=feature,
    )
    returned = data.get("feature", {})
    status = (data.get("featureState") or {}).get("featureStatus")
    return _feature_summary(returned, status)


def delete_feature(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
) -> dict[str, Any]:
    data = client.request_json(
        "DELETE",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}"
        f"/features/featureid/{feature_id}",
    )
    return {"deleted": feature_id, "featureStatus": data.get("featureState", {}).get("featureStatus") if isinstance(data, dict) else None}


def eval_featurescript(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    script: str,
    queries: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """POST a FeatureScript function for evaluation. `script` must be a full
    function, e.g.: function(context is Context, queries) { return ...; }

    `queries` is a MAP of name -> list of transient ids (the live API rejects
    an array here), exposed to the script via its `queries` parameter."""
    data = client.request_json(
        "POST",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/featurescript",
        json_body={"script": script, "queries": queries or {}},
    )
    result = {"result": unwrap_fs_value(data.get("result"))}
    notices = data.get("notices") or []
    if notices:
        result["notices"] = notices
    return result
