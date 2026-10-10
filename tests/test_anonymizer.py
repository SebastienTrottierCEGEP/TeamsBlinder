"""
Tests unitaires pour TeamsBlinder (anonymizer).
"""

import os
import shutil
import tempfile
import unittest
import zipfile

from anonymizer.identity import extract_student_identity, MappingTracker
from anonymizer.file_operations import (
    find_latest_version_dir,
    extract_zip_archives,
    anonymize_text_content,
    generate_name_patterns,
    prepare_student_submission,
)


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
