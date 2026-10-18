#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Безопасные тесты правил проверки названий станций."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

import update_stations as parser


class TestStationNameValidation(unittest.TestCase):

    def test_operations_codes_are_rejected(self):
        """Коды коммерческих операций не должны быть названием."""
        self.assertFalse(parser.valid_name("8н,10н"))
        self.assertFalse(parser.valid_name("3,8н,10н"))

    def test_station_name_with_number_is_allowed(self):
        """Цифра в настоящем названии не делает его ошибочным."""
        self.assertTrue(parser.valid_name("Сортировочная-2"))

    def test_regular_station_name_is_allowed(self):
        """Обычные названия станций должны проходить проверку."""
        self.assertTrue(parser.valid_name("Брест-Северный"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
