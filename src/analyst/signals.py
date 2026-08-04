"""The Signal record every detector emits, and the severity vocabulary.

Severity is a *routing* hint, not an opinion:
- `critical` — the stored numbers themselves cannot be trusted as printed
  (a unit switch, a ~1000× cross-period break). Blocks comparison outright.
- `alert`   — the numbers are real but the comparison basis moved (restatement,
  opinion change, divergence, perimeter event). The memo must carry it.
- `notice`  — worth a line in the comparability caveats, nothing more
  (auditor rotation, P&L structure change, report-kind rhythm break).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SEVERITIES = ("notice", "alert", "critical")

SIGNAL_TYPES = (
    "unit_change",
    "cross_period_mismatch",
    "opinion_change",
    "perimeter_change",
    "divergence",
)


@dataclass(frozen=True)
class Signal:
    signal_type: str
    subtype: str            # lane / discriminator; "" when the type needs none
    bank_ticker: str
    period: str
    kind: str
    severity: str
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.signal_type not in SIGNAL_TYPES:
            raise ValueError(f"unknown signal_type {self.signal_type!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}")

    @property
    def signal_id(self) -> str:
        """Stable id, PK in analyst_signals. Subtype is part of identity so two
        lanes firing on the same partition stay two rows."""
        parts = [self.signal_type]
        if self.subtype:
            parts.append(self.subtype)
        parts += [self.bank_ticker, self.period, self.kind]
        return ":".join(parts)

    def to_row(self) -> dict:
        """The analyst_signals row shape (payload JSON-encoded)."""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "bank_ticker": self.bank_ticker,
            "period": self.period,
            "kind": self.kind,
            "severity": self.severity,
            "payload": json.dumps(
                {"subtype": self.subtype, **self.payload} if self.subtype else self.payload,
                ensure_ascii=False, sort_keys=True,
            ),
        }
