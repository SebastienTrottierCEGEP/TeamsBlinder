"""
Tests unitaires pour TeamsBlinder (anonymizer).
"""

import os
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from anonymizer.agent_harness import AgentLoopGuard, AgentLoopLimitError, AnonymizationAgentHarness
from anonymizer.identity import (
    extract_student_identity,
    split_first_last_name,
    get_student_sort_key,
    MappingTracker,
)
from anonymizer.file_operations import (
    find_latest_version_dir,
    extract_zip_archives,
    anonymize_text_content,
    generate_name_patterns,
    prepare_student_submission,
)


AGENT_CONFIG = {
    "model_id": "configured-model",
    "agent_max_turns": "7",
    "agent_max_tool_calls": "11",
    "agent_max_repeated_calls": "2",
}


class TestAnonymizationAgentHarness(unittest.TestCase):
    @patch("anonymizer.agent_harness.load_config", return_value=AGENT_CONFIG)
    def test_model_id_defaults_to_configured_value(self, load_config):
        harness = AnonymizationAgentHarness()

        self.assertEqual(harness.model_id, "configured-model")
        load_config.assert_called_once_with()

    @patch("anonymizer.agent_harness.load_config", return_value=AGENT_CONFIG)
    def test_explicit_model_id_overrides_config(self, load_config):
        harness = AnonymizationAgentHarness(model_id="override-model")

        self.assertEqual(harness.model_id, "override-model")

    @patch("anonymizer.agent_harness.load_config", return_value=AGENT_CONFIG)
    def test_loop_limits_come_from_config(self, load_config):
        harness = AnonymizationAgentHarness()

        self.assertEqual(
            (harness.max_turns, harness.max_tool_calls, harness.max_repeated_calls), (7, 11, 2)
        )

    @patch("anonymizer.agent_harness.load_config", return_value=AGENT_CONFIG)
    @patch("urllib.request.urlopen", side_effect=Exception("Connection refused"))
    def test_is_available_returns_false_when_offline(self, mock_urlopen, load_config):
        harness = AnonymizationAgentHarness()
        self.assertFalse(harness.is_available(timeout=0.1))
        is_online, msg = harness.check_availability(timeout=0.1)
        self.assertFalse(is_online)
        self.assertIn("injoignable", msg)

    @patch("anonymizer.agent_harness.load_config", return_value=AGENT_CONFIG)
    @patch.object(AnonymizationAgentHarness, "is_available", return_value=False)
    def test_discover_aliases_does_not_attempt_when_ollama_offline(self, mock_is_available, load_config):
        harness = AnonymizationAgentHarness()
        aliases = harness.discover_aliases(
            student_name="Test Student",
            da="1234567",
            alias="etudiant01",
            filenames=["test.txt"],
            snippets=["test"],
        )
        self.assertEqual(aliases, [])


class TestAgentLoopGuard(unittest.TestCase):
    def test_repeated_identical_calls_trip_guard(self):
        guard = AgentLoopGuard(max_repeated_calls=2)
        self.assertIsNone(guard.record_tool_call("list_files", "."))
        self.assertIsNone(guard.record_tool_call("list_files", "."))
        self.assertIsNotNone(guard.record_tool_call("list_files", "."))
        with self.assertRaises(AgentLoopLimitError):
            guard.check()

    def test_distinct_calls_do_not_trip_repeat_limit(self):
        guard = AgentLoopGuard(max_repeated_calls=1)
        self.assertIsNone(guard.record_tool_call("read_file_content", "a.txt"))
        self.assertIsNone(guard.record_tool_call("read_file_content", "b.txt"))
        guard.check()

    def test_total_tool_calls_limit(self):
        guard = AgentLoopGuard(max_tool_calls=2)
        guard.record_tool_call("rename_file", "a", "b")
        guard.record_tool_call("rename_file", "c", "d")
        self.assertIsNotNone(guard.record_tool_call("rename_file", "e", "f"))
        with self.assertRaises(AgentLoopLimitError):
            guard.check()

    def test_turn_limit(self):
        guard = AgentLoopGuard(max_turns=1)
        guard.record_turn()
        guard.check()
        guard.record_turn()
        with self.assertRaises(AgentLoopLimitError):
            guard.check()


class TestIdentityExtraction(unittest.TestCase):
    def test_standard_teams_format(self):
        name, da = extract_student_identity("Gaetan Simard (2244612)")
        self.assertEqual(name, "Gaetan Simard")
        self.assertEqual(da, "2244612")

    def test_format_with_spaces_and_parentheses(self):
        name, da = extract_student_identity("Jean-Francois Tremblay ( 1234567 )")
        self.assertEqual(name, "Jean-Francois Tremblay")
        self.assertEqual(da, "1234567")

    def test_format_with_underscore(self):
        name, da = extract_student_identity("Alice Martin_7654321")
        self.assertEqual(name, "Alice Martin")
        self.assertEqual(da, "7654321")

    def test_split_first_last_name(self):
        self.assertEqual(split_first_last_name("Gaetan Simard"), ("Simard", "Gaetan"))
        self.assertEqual(split_first_last_name("Simard, Gaetan"), ("Simard", "Gaetan"))
        self.assertEqual(split_first_last_name("Evelyne Gordon-Manningham"), ("Gordon-Manningham", "Evelyne"))
        self.assertEqual(split_first_last_name("Mavrick Roy-Giasson"), ("Roy-Giasson", "Mavrick"))
        self.assertEqual(split_first_last_name("Esai Emmanuel Kouevi"), ("Kouevi", "Esai Emmanuel"))
        self.assertEqual(split_first_last_name("Ayoub Aziz Michel Berraud"), ("Berraud", "Ayoub Aziz Michel"))
        self.assertEqual(split_first_last_name("Emmanuel Claude Mbessa Nneme"), ("Mbessa Nneme", "Emmanuel Claude"))

    def test_alphabetical_sorting_by_last_name(self):
        student_folders = [
            "Gaetan Simard (2244612)",
            "Ayoub Aziz Michel Berraud (2352341)",
            "Mavrick Roy-Giasson (2538152)",
            "Evelyne Gordon-Manningham (2539142)",
            "Emmanuel Claude Mbessa Nneme (2341347)",
        ]
        sorted_folders = sorted(student_folders, key=get_student_sort_key)
        self.assertEqual(
            sorted_folders,
            [
                "Ayoub Aziz Michel Berraud (2352341)",    # B
                "Evelyne Gordon-Manningham (2539142)",    # G
                "Emmanuel Claude Mbessa Nneme (2341347)", # M
                "Mavrick Roy-Giasson (2538152)",         # R
                "Gaetan Simard (2244612)",                # S
            ],
        )


class TestMappingTracker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mapping_file = os.path.join(self.temp_dir, "mapping.csv")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_alias_generation_and_idempotence(self):
        tracker = MappingTracker(self.mapping_file, prefix="etudiant")
        alias1 = tracker.get_or_create_alias("Gaetan Simard", "2244612", "/src/1", "/dst/1", "Exam1")
        self.assertEqual(alias1, "etudiant01")

        alias2 = tracker.get_or_create_alias("Alice Martin", "7654321", "/src/2", "/dst/2", "Exam1")
        self.assertEqual(alias2, "etudiant02")

        # Idempotence : même étudiant doit garder le même alias
        alias1_bis = tracker.get_or_create_alias("Gaetan Simard", "2244612", "/src/1", "/dst/1", "Exam1")
        self.assertEqual(alias1_bis, "etudiant01")


class TestVersionResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_select_highest_version(self):
        v1 = os.path.join(self.temp_dir, "Version 1")
        v2 = os.path.join(self.temp_dir, "Version 2")
        v3 = os.path.join(self.temp_dir, "Version 3")
        os.makedirs(v1)
        os.makedirs(v2)
        os.makedirs(v3)

        latest_path, v_num = find_latest_version_dir(self.temp_dir)
        self.assertEqual(v_num, 3)
        self.assertEqual(latest_path, v3)


class TestZipExtraction(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_extract_and_remove_zip(self):
        zip_path = os.path.join(self.temp_dir, "test_archive.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test_file.txt", "Contenu de test")

        self.assertTrue(os.path.exists(zip_path))
        extracted = extract_zip_archives(self.temp_dir)
        self.assertEqual(extracted, 1)

        # L'archive .zip doit avoir été supprimée
        self.assertFalse(os.path.exists(zip_path))
        # Le fichier extrait doit être présent
        extracted_file = os.path.join(self.temp_dir, "test_file.txt")
        self.assertTrue(os.path.exists(extracted_file))


class TestTextAnonymization(unittest.TestCase):
    def test_anonymize_name_and_da(self):
        raw_text = (
            "// v2 de Gaetan Simard 2344612\n"
            "void f() {\n"
            '  string db = "simard_gaetan.db";\n'
            "  // Auteur : GaetanSimard\n"
            "}\n"
        )
        patterns = generate_name_patterns("Gaetan Simard")
        modified, count = anonymize_text_content(raw_text, "etudiant01", patterns, da="2244612")

        self.assertNotIn("Gaetan Simard", modified)
        self.assertNotIn("simard_gaetan", modified)
        self.assertNotIn("GaetanSimard", modified)
        self.assertNotIn("2344612", modified)
        self.assertIn("etudiant01", modified)
        self.assertIn("XXXXXXX", modified)


if __name__ == "__main__":
    unittest.main()
