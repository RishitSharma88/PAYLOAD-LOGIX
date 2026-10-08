"""Lightweight deterministic CAG/retrieval over NASA SOA-2026 extracts.

NOT training: the SLM weights are never touched. This module fetches
relevant NASA context (terminology, categories, components, tables) with
source provenance and feeds it into the orchestrator prompt.

Sources (all local, pre-existing):
  - soa-2026.pdf                      (authoritative document, not parsed here)
  - soa-2026_tables_index.csv         (table title -> page)
  - payload_logix_data/processed/components_master_clean.csv (components)
"""
import csv
import os
import re
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = "soa-2026.pdf"

# Internal protocol category -> SOA dataset category names (aliases).
CATEGORY_ALIASES = {
    "RADIO": ["radios"],
    "REACTION_WHEEL": ["high heritage miniature reaction wheels",
                       "reaction wheel", "reaction wheels"],
    "PMAD": ["power management and distribution system products",
             "power management", "pmad"],
}

# Deterministic component-id prefixes per protocol category.
ID_PREFIX = {"RADIO": "RADIO", "REACTION_WHEEL": "HHMRW", "PMAD": "PMAD"}

_WORD = re.compile(r"[a-z0-9]+")

# Generic query/unit tokens that would otherwise match every record.
STOPWORDS = {"mass", "power", "volume", "weight", "size", "add", "adding",
             "want", "need", "needs", "with", "component", "components",
             "payload", "the", "a", "an", "to", "of", "for", "in", "on",
             "and", "or", "below", "above", "less", "than", "total",
             "kg", "g", "w", "cm", "cm3", "s", "i", "it", "is"}


def _norm(tok):
    # Light singularization so "radios" matches "radio", etc.
    if len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _tokens(text):
    return {_norm(t) for t in _WORD.findall((text or "").lower())
            } - STOPWORDS


class NasaRetriever:
    def __init__(self, base=BASE):
        self.base = base
        self.tables = []      # [{title, page}]
        self.components = []  # [{id, category, name, manufacturer, specs, source}]
        self._load()

    # -- loading ---------------------------------------------------------
    def _load(self):
        with open(os.path.join(self.base, "soa-2026_tables_index.csv")) as f:
            for row in csv.DictReader(f):
                self.tables.append({"title": row["table_title"],
                                    "page": row["page"]})
        master = os.path.join(self.base, "payload_logix_data", "processed",
                              "components_master_clean.csv")
        by_cat = defaultdict(list)
        with open(master) as f:
            for row in csv.DictReader(f):
                by_cat[row["category"]].append(row)
        for proto_cat, aliases in CATEGORY_ALIASES.items():
            wanted = set(aliases)
            rows = []
            for cat, rs in by_cat.items():
                if cat.lower() in wanted:
                    rows.extend(rs)
            rows.sort(key=lambda r: (r.get("component_name") or ""))
            for i, r in enumerate(rows, 1):
                specs = self._spec_line(r)
                self.components.append({
                    "id": "%s_%03d" % (ID_PREFIX[proto_cat], i),
                    "proto_category": proto_cat,
                    "soa_category": r["category"],
                    "name": r.get("component_name") or "",
                    "manufacturer": r.get("manufacturer") or "",
                    "specs": specs,
                    "source": {"document": DOC,
                               "page": self._page_for(r["category"]),
                               "table": self._table_for(r["category"])},
                })

    @staticmethod
    def _num(r, key):
        v = (r.get(key) or "").strip()
        return v if v not in ("", "nan", "None") else None

    def _spec_line(self, r):
        parts = []
        m = self._num(r, "mass_kg")
        # NOTE: stored mass_kg is gram-scale for Radios, true kg otherwise
        # (pipeline quirk); protocol layer normalizes to kg on entry.
        if m: parts.append("mass=%s (stored mass_kg)" % m)
        p = self._num(r, "power_w")
        if p: parts.append("power=%s W" % p)
        v = self._num(r, "volume_cm3") or self._num(r, "dimension_volume_cm3")
        if v: parts.append("volume=%s cm3" % v)
        for k, label in (("frequency_or_band", "band"),
                         ("performance_or_capacity", "perf"),
                         ("flight_heritage_or_orbit", "heritage")):
            if (r.get(k) or "").strip():
                parts.append("%s=%s" % (label, r[k].strip()[:60]))
        return "; ".join(parts)

    def _table_for(self, soa_category):
        key = soa_category.lower()
        for t in self.tables:
            if key in t["title"].lower():
                return t["title"]
        return ""

    def _page_for(self, soa_category):
        t = self._table_for(soa_category)
        for row in self.tables:
            if row["title"] == t:
                return row["page"]
        return ""

    # -- retrieval -------------------------------------------------------
    def retrieve(self, query, top_k=5):
        """Return top_k context items, each {text, source} with provenance."""
        qtok = _tokens(query)
        # Expand protocol-category aliases present in the query.
        hits = []
        for c in self.components:
            score = 0
            hay = _tokens("%s %s %s %s" % (c["name"], c["manufacturer"],
                                           c["soa_category"], c["specs"]))
            score += len(qtok & hay)
            # Category-level match: query mentions the family.
            for alias in CATEGORY_ALIASES[c["proto_category"]]:
                if _tokens(alias) & qtok:
                    score += 3
                    break
            if score > 0:
                hits.append((score, c))
        hits.sort(key=lambda h: (-h[0], h[1]["id"]))
        out = []
        for _, c in hits[:top_k]:
            out.append({
                "text": "[%s] %s (%s) -- %s" % (c["id"], c["name"],
                                                c["manufacturer"], c["specs"]),
                "source": dict(c["source"], record=c["id"]),
            })
        # Always ground the category itself when mentioned.
        for proto_cat, aliases in CATEGORY_ALIASES.items():
            alias_tok = set()
            for a in aliases:
                alias_tok |= _tokens(a)
            if alias_tok & qtok:
                soa = [c["soa_category"] for c in self.components
                       if c["proto_category"] == proto_cat]
                if soa:
                    out.append({
                        "text": "Category %s = SOA '%s' (%d records)" %
                                (proto_cat, soa[0],
                                 sum(1 for c in self.components
                                     if c["proto_category"] == proto_cat)),
                        "source": {"document": DOC,
                                   "page": self._page_for(soa[0]),
                                   "table": self._table_for(soa[0])},
                    })
                break
        return out

    def format_context(self, query, top_k=5):
        items = self.retrieve(query, top_k)
        if not items:
            return "CAG CONTEXT: no matching NASA SOA-2026 records found."
        lines = ["CAG CONTEXT (NASA SOA-2026, soa-2026.pdf):"]
        for it in items:
            s = it["source"]
            lines.append("- %s [doc=%s p.%s table='%s' record=%s]" %
                         (it["text"], s["document"], s.get("page", "?"),
                          (s.get("table") or "")[:60], s.get("record", "-")))
        return "\n".join(lines)
