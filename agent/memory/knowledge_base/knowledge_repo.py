"""Knowledge repository — indexed access to accumulated facts.

Wraps the state's observed_facts with lookup by type, subject, confidence.
Isolation: no expected-data references.
"""


class KnowledgeRepository:
    """Read-only indexed view over state facts.

    Usage:
        repo = KnowledgeRepository(state_manager.get_state()["observed_facts"])
        sqli_findings = repo.findings_by_type("sqli")
    """

    def __init__(self, facts=None):
        self._facts = list(facts or [])
        self._by_type = {}
        self._by_subject = {}
        self._reindex()

    def _reindex(self):
        self._by_type.clear()
        self._by_subject.clear()
        for f in self._facts:
            ft = f.get("fact_type", "")
            subj = f.get("subject", "")
            self._by_type.setdefault(ft, []).append(f)
            self._by_subject.setdefault(subj, []).append(f)

    def update(self, facts):
        """Replace facts and rebuild indexes."""
        self._facts = list(facts)
        self._reindex()

    @property
    def all_facts(self):
        return list(self._facts)

    def by_type(self, fact_type):
        """Return facts of given type."""
        return list(self._by_type.get(fact_type, []))

    def by_subject(self, subject):
        """Return facts for given subject (target_id)."""
        return list(self._by_subject.get(subject, []))

    def findings(self, min_confidence=0.0):
        """Return CANDIDATE_FINDING + CONFIRMED_FINDING above threshold."""
        return [
            f for f in self._facts
            if f.get("fact_type") in ("CANDIDATE_FINDING", "CONFIRMED_FINDING")
            and f.get("confidence", 0) >= min_confidence
        ]

    def findings_by_type(self, finding_type, min_confidence=0.0):
        """Return findings whose value starts with finding_type."""
        return [
            f for f in self.findings(min_confidence)
            if str(f.get("value", "")).startswith(finding_type)
        ]

    def services(self):
        """Return all SERVICE facts."""
        return self.by_type("SERVICE")

    def endpoints(self):
        """Return all ENDPOINT facts."""
        return self.by_type("ENDPOINT")

    def fact_types(self):
        """Return set of distinct fact_types present."""
        return set(self._by_type.keys())

    def subjects(self):
        """Return set of distinct subjects present."""
        return set(self._by_subject.keys())
