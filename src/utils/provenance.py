"""
Provenance Filter — Cross-Document Contamination Guard.

Ensures every relationship in the output can be traced back to a tag that was
actually extracted from the PRIMARY input PDF, not from reference/legend sheets
uploaded alongside it.

Usage in CompilerAgent:
    from src.utils.provenance import build_ocr_token_set, filter_relationships_by_provenance
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, List, Set, Tuple

logger = logging.getLogger(__name__)

# Regex to canonicalize a tag for provenance matching: strip area prefix, uppercase
_PREFIX_RE = re.compile(r'^\d{2,3}-', re.IGNORECASE)


def _canonical(tag: str) -> str:
    """Strip leading unit prefix and uppercase for provenance comparison."""
    return _PREFIX_RE.sub('', tag.strip().upper())


def build_ocr_token_set(ocr_items: List[Dict[str, Any]]) -> Set[str]:
    """
    Build a set of canonical tag strings from the primary PDF's OCR result.
    Both raw and canonicalized forms are stored so either variant matches.

    Args:
        ocr_items: List of classified items from classify_paddle_results().

    Returns:
        Set of uppercase tag strings (raw + canonical, no area prefix).
    """
    token_set: Set[str] = set()
    for item in ocr_items:
        tag = item.get('tag') or item.get('text') or item.get('value') or ''
        if tag:
            raw = tag.strip().upper()
            canon = _canonical(raw)
            token_set.add(raw)
            token_set.add(canon)
    logger.info(f"Provenance: built token set with {len(token_set)} entries from {len(ocr_items)} OCR items.")
    return token_set


def filter_relationships_by_provenance(
    relations: List[Dict[str, Any]],
    token_set: Set[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filter out relationship edges where BOTH source and target tags are absent
    from the primary PDF's OCR token set — these are cross-document contamination.

    A relationship is kept if EITHER the source OR target appears in the primary
    document's token set (one legitimate anchor is sufficient to keep an edge).
    Both must be absent for the edge to be dropped.

    Args:
        relations:  List of relationship dicts with 'source_tag', 'target_tag', 'rel_type'.
        token_set:  Set returned by build_ocr_token_set() for the primary PDF.

    Returns:
        (clean_relations, dropped_relations) tuple.
    """
    clean: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []

    for rel in relations:
        src = (rel.get('source_tag') or rel.get('source') or '').strip().upper()
        tgt = (rel.get('target_tag') or rel.get('target') or '').strip().upper()

        src_in = src in token_set or _canonical(src) in token_set
        tgt_in = tgt in token_set or _canonical(tgt) in token_set

        if not src_in and not tgt_in:
            # Both tags are foreign — cross-document contamination
            logger.warning(
                f"Provenance DROP: '{src}' → '{tgt}' "
                f"— neither tag found in primary PDF OCR."
            )
            dropped.append({**rel, 'flag_reason': 'cross_document_contamination'})
        else:
            clean.append(rel)

    if dropped:
        logger.info(
            f"Provenance filter: kept {len(clean)}, dropped {len(dropped)} "
            f"cross-document relationships."
        )
    else:
        logger.info(f"Provenance filter: all {len(clean)} relationships verified clean.")

    return clean, dropped
