"""Complete-link refinement for KR daily issue clusters.

Pairwise union-find can chain A-B and B-C even when A-C describe different
events. This refinement keeps a document only with members it directly matches.
"""
from __future__ import annotations

import hashlib


def refine_clusters(clusters: list[dict], *, similarity, minimum: float = 0.58) -> list[dict]:
    refined: list[dict] = []
    for cluster in clusters or []:
        buckets: list[list[dict]] = []
        for doc in cluster.get("docs") or []:
            compatible = [
                (index, min((float(similarity(doc, member)) for member in members), default=1.0))
                for index, members in enumerate(buckets)
            ]
            eligible = [row for row in compatible if row[1] >= minimum]
            if eligible:
                index = max(eligible, key=lambda row: row[1])[0]
                buckets[index].append(doc)
            else:
                buckets.append([doc])
        for members in buckets:
            keys = sorted(str(row.get("id") or row.get("path") or row.get("url") or row.get("title") or "") for row in members)
            issue_id = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:16]
            pair_scores = [
                float(similarity(left, right))
                for index, left in enumerate(members)
                for right in members[index + 1:]
            ]
            refined.append({
                "issueId": issue_id,
                "clusterConfidence": round(min(pair_scores), 4) if pair_scores else 1.0,
                "docs": members,
                "coherencePolicy": "complete_link",
            })
    return refined


__all__ = ["refine_clusters"]
