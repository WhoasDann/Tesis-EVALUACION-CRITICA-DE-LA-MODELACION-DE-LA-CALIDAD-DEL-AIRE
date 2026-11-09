import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tesis.vinculo_horario import validar_vinculo_horario


class VinculoHorarioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.control = self.root/'aermod.inp'
        self.sources = self.root/'fuentes.inc'
        self.emissions = self.root/'MP10.emi'
        self.control.write_text('SO HOUREMIS MP10.emi N000001-N000002\n')
        self.sources.write_text('SO LOCATION N000001 LINE 0 0 0 50 0\nSO LOCATION N000002 LINE 50 0 0 100 0\n')
        self.lines = ['SO HOUREMIS 16 12 21 1 N000001 0.1\n',
                      'SO HOUREMIS 16 12 21 1 N000002 0.2\n']
        self.emissions.write_text(''.join(self.lines))

    def validate(self):
        return validar_vinculo_horario(self.control,self.sources,self.emissions,{(16,12,21,1)})

    def test_valid_binding(self):
        self.assertEqual(self.validate()['filas'],2)

    def test_original_defect_old_range_is_rejected(self):
        self.control.write_text('SO HOUREMIS MP10.emi L000001-L001651\n')
        with self.assertRaisesRegex(ValueError,'HOUREMIS'):
            self.validate()

    def test_same_count_wrong_prefix_is_rejected(self):
        self.control.write_text('SO HOUREMIS MP10.emi L000001-L000002\n')
        with self.assertRaisesRegex(ValueError,'HOUREMIS'):
            self.validate()

    def test_missing_or_duplicate_source_is_rejected(self):
        for lines in [self.lines[:1],self.lines+[self.lines[0]]]:
            with self.subTest(lines=lines):
                self.emissions.write_text(''.join(lines))
                with self.assertRaises(ValueError):
                    self.validate()

    def test_wrong_hour_source_and_rate_are_rejected(self):
        for line in ['SO HOUREMIS 16 12 21 2 N000002 0.2\n',
                     'SO HOUREMIS 16 12 21 1 L000002 0.2\n',
                     'SO HOUREMIS 16 12 21 1 N000002 nan\n']:
            with self.subTest(line=line):
                self.emissions.write_text(self.lines[0]+line)
                with self.assertRaises(ValueError):
                    self.validate()


if __name__ == '__main__':
    unittest.main()
