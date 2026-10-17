"""
Tests unitaires pour deanonymize (TeamsBlinder).
"""

import os
import shutil
import tempfile
import unittest

from deanonymize import (
    get_output_filepath,
    load_mappings,
    deanonymize_text,
    process_file,
)


class TestDeanonymize(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mapping_file = os.path.join(self.temp_dir, "mapping_test.csv")
        with open(self.mapping_file, "w", encoding="utf-8") as f:
            f.write(
                "alias,student_name,da,source_folder,destination_folder,exam_name,timestamp\n"
                "etudiant01,Ard Gre Hty,2032212,/src/1,/dst/1,Exam1,2026-10-10\n"
                "etudiant02,BArd Dre Gre Htr,2032219,/src/2,/dst/2,Exam1,2026-10-10\n"
                "etudiant04,Gaetan Simard,2244612,/src/4,/dst/4,Exam1,2026-10-10\n"
                "etudiant10,Carl Tuters,2032456,/src/10,/dst/10,Exam1,2026-10-10\n"
            )
        self.mappings = load_mappings(self.mapping_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_output_filepath_generation(self):
        # 1. Extension standard
        out1 = get_output_filepath("/path/to/notes.txt")
        self.assertEqual(out1, os.path.abspath("/path/to/notes_out.txt"))

        # 2. Fichier CSV
        out2 = get_output_filepath("resultats.csv")
        self.assertEqual(os.path.basename(out2), "resultats_out.csv")

        # 3. Fichier sans extension
        out3 = get_output_filepath("/tmp/Makefile")
        self.assertEqual(out3, os.path.abspath("/tmp/Makefile_out"))

        # 4. Fichier avec plusieurs extensions/points
        out4 = get_output_filepath("my.grades.final.txt")
        self.assertEqual(os.path.basename(out4), "my.grades.final_out.txt")

    def test_single_student_file_deanonymization(self):
        sample = (
            "// v2 de etudiant04 XXXXXXX\n"
            "void f() {\n"
            '  string db = "etudiant04.db";\n'
            "  // Matricule : XXXXXXX\n"
            "}\n"
        )
        res, stats = deanonymize_text(sample, self.mappings)
        self.assertNotIn("etudiant04", res)
        self.assertNotIn("XXXXXXX", res)
        self.assertIn("Gaetan Simard", res)
        self.assertIn("2244612", res)
        self.assertEqual(stats["aliases_replaced"], 2)
        self.assertEqual(stats["das_replaced"], 2)

    def test_multi_student_csv_deanonymization(self):
        sample = (
            "alias,da,note\n"
            "etudiant01,XXXXXXX,95\n"
            "etudiant02,XXXXXXX,88\n"
            "etudiant10,XXXXXXX,92\n"
        )
        res, stats = deanonymize_text(sample, self.mappings)
        self.assertIn("Ard Gre Hty,2032212,95", res)
        self.assertIn("BArd Dre Gre Htr,2032219,88", res)
        self.assertIn("Carl Tuters,2032456,92", res)
        self.assertNotIn("etudiant01", res)
        self.assertNotIn("etudiant02", res)
        self.assertNotIn("etudiant10", res)
        self.assertNotIn("XXXXXXX", res)

    def test_alias_without_da(self):
        sample = "Rapport préparé par etudiant01 pour la session."
        res, stats = deanonymize_text(sample, self.mappings)
        self.assertEqual(res, "Rapport préparé par Ard Gre Hty pour la session.")
        self.assertEqual(stats["aliases_replaced"], 1)
        self.assertEqual(stats["das_replaced"], 0)

    def test_two_lines_name_then_da(self):
        sample = (
            "Nom de l'étudiant : etudiant01\n"
            "DA : XXXXXXX\n"
        )
        res, stats = deanonymize_text(sample, self.mappings)
        self.assertIn("Nom de l'étudiant : Ard Gre Hty\nDA : 2032212", res)
        self.assertNotIn("etudiant01", res)
        self.assertNotIn("XXXXXXX", res)

    def test_two_lines_da_then_name_multiple_students(self):
        sample = (
            "Fiche 1:\n"
            "DA : XXXXXXX\n"
            "Nom de l'étudiant : etudiant01\n"
            "\n"
            "Fiche 2:\n"
            "DA : XXXXXXX\n"
            "Nom de l'étudiant : etudiant02\n"
        )
        res, stats = deanonymize_text(sample, self.mappings)
        self.assertIn("DA : 2032212\nNom de l'étudiant : Ard Gre Hty", res)
        self.assertIn("DA : 2032219\nNom de l'étudiant : BArd Dre Gre Htr", res)
        self.assertNotIn("etudiant01", res)
        self.assertNotIn("etudiant02", res)
        self.assertNotIn("XXXXXXX", res)

    def test_append_da_option(self):
        sample = "Note finale pour etudiant01 : 100%"
        res, stats = deanonymize_text(sample, self.mappings, append_da_to_name=True)
        self.assertEqual(res, "Note finale pour Ard Gre Hty (2032212) : 100%")

    def test_process_file_end_to_end(self):
        input_file = os.path.join(self.temp_dir, "evaluation.txt")
        with open(input_file, "w", encoding="utf-8") as f:
            f.write("Étudiant: etudiant04 | DA: XXXXXXX | Note: A+\n")

        out_path, stats = process_file(input_file, mapping_file=self.mapping_file)
        expected_out = os.path.join(self.temp_dir, "evaluation_out.txt")
        self.assertEqual(out_path, expected_out)
        self.assertTrue(os.path.exists(expected_out))

        with open(expected_out, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Gaetan Simard", content)
        self.assertIn("2244612", content)
        self.assertNotIn("etudiant04", content)
        self.assertNotIn("XXXXXXX", content)


if __name__ == "__main__":
    unittest.main()
