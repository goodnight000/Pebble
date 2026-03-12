from __future__ import annotations

import re

from app.models import EventType


_RULES = [
    (EventType.STARTUP_FUNDING, re.compile(r"\b(series\s+a|series\s+b|raises|funding|seed)\b", re.I)),
    (EventType.M_AND_A, re.compile(r"\b(acquires|acquisition|merger)\b", re.I)),
    (EventType.OPEN_SOURCE_RELEASE, re.compile(r"\b(open[-\s]?source|github|repo|released on github)\b", re.I)),
    (EventType.CHIP_HARDWARE, re.compile(r"\b(gpu|hbm|tpu|accelerator|chip)\b", re.I)),
    (
        EventType.GOVERNMENT_ACTION,
        re.compile(r"\b(executive order|white house|congress|senate|house bill|ftc|nist|regulator)\b", re.I),
    ),
    (EventType.POLICY_REGULATION, re.compile(r"\b(policy|regulation|ban|eu ai act)\b", re.I)),
    (EventType.SECURITY_INCIDENT, re.compile(
        r"\b("
        r"vulnerability|vulnerabilities|"
        r"leak|breach|data breach|"
        r"security incident|security flaw|"
        r"CVE-\d{4}-\d+|"
        r"zero[- ]day|0[- ]day|"
        r"ransomware|malware|trojan|"
        r"exploit|exploited|exploitation|"
        r"remote code execution|RCE|"
        r"privilege escalation|"
        r"supply[- ]chain attack|"
        r"phishing|spear[- ]phishing|"
        r"APT|advanced persistent threat|"
        r"backdoor|rootkit|"
        r"critical patch|"
        r"security advisory|"
        r"SQL injection|XSS|CSRF|SSRF"
        r")\b",
        re.I,
    )),
    (EventType.BENCHMARK_RESULT, re.compile(r"\b(benchmark|sota|state-of-the-art)\b", re.I)),
    (EventType.MODEL_RELEASE, re.compile(r"\b(releases|launches|introduces|announces)\b.*\bmodel\b", re.I)),
]


def classify_event_type(title: str, source_kind: str | None = None) -> EventType:
    if source_kind == "arxiv":
        return EventType.RESEARCH_PAPER
    if source_kind == "nvd":
        return EventType.SECURITY_INCIDENT
    for event_type, pattern in _RULES:
        if pattern.search(title):
            return event_type
    return EventType.OTHER
