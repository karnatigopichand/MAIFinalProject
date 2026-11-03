"""Deterministic tests for the local Impact Investigation Agent prototype."""
from pathlib import Path
import unittest

from agents.impact import ImpactInvestigationAgent, LocalCorpusTools, Ticket

ROOT = Path(__file__).resolve().parents[1]


class ImpactAgentTests(unittest.TestCase):
    def setUp(self):
        self.tools = LocalCorpusTools(ROOT / "sample-repositories")
        self.agent = ImpactInvestigationAgent(self.tools)

    def test_delivery_change_finds_source_and_explicit_downstream_paths(self):
        result = self.agent.investigate(Ticket(
            "SHOP-101", "Pass delivery instructions from checkout to shipping",
            "Include delivery instructions in the carrier shipment request.",
            ("The carrier receives the instructions supplied at checkout.",),
        ))
        repos = {finding.repository for finding in result.findings}
        self.assertIn("commerce-checkout", repos)
        self.assertIn("commerce-orders", repos)
        self.assertIn("commerce-shipping", repos)
        self.assertTrue(result.evidence)
        self.assertTrue(any("PUBLISHES" in path.relationships or "CONSUMES" in path.relationships for path in result.dependency_paths))
        self.assertTrue(any(finding.classification == "change_required" for finding in result.findings))
        self.assertIn("Jira, Pinecone, and Neo4j are not connected. Related issue keys mentioned in the input are not looked up or verified.", result.limitations)

    def test_ambiguous_request_returns_questions_and_markdown(self):
        result = self.agent.investigate(Ticket("PROPOSED-CHANGE", "Make shipping faster and better"))
        self.assertEqual(result.status, "needs_clarification")
        self.assertTrue(result.questions)
        self.assertIn("## Questions and limitations", result.to_markdown())

    def test_snapshot_mismatch_is_rejected_by_tool(self):
        with self.assertRaises(ValueError):
            self.tools.search_docs("delivery address", "some-other-snapshot")

    def test_unrelated_request_reports_scope_limitation(self):
        result = self.agent.investigate(Ticket("NEW-1", "Support lunar cargo teleportation"))
        self.assertFalse(result.findings)
        self.assertTrue(any("No matching local evidence" in item for item in result.limitations))


if __name__ == "__main__":
    unittest.main()
