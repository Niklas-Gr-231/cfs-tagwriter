# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import unittest
from pathlib import Path
from cfs_release_notes import note_blocks,parse_history,release_history
from cfs_versions import APP_VERSION


class ReleaseNotes(unittest.TestCase):
    def test_source_wrapping_is_not_a_display_line_break(self):
        blocks=note_blocks('**3.7.1 · Neue Version**\n\n- Erster Satz\n  mit Fortsetzung.\n- Zweiter Punkt mit **Betonung** und `Code`.\n\nEin Absatz\nmit Fortsetzung.')
        self.assertEqual(blocks,[('heading','3.7.1 · Neue Version'),('bullet','Erster Satz mit Fortsetzung.'),('bullet','Zweiter Punkt mit Betonung und Code.'),('body','Ein Absatz mit Fortsetzung.')])

    def test_history_keeps_version_sections_separate_in_numeric_order(self):
        entries=parse_history('# Änderungen\n\n**3.9.0 · Alt**\n\n- Alt\n\n**3.10.0 · Neu**\n\n- Neu\n')
        self.assertEqual([entry['version'] for entry in entries],['3.10.0','3.9.0'])
        self.assertNotIn('- Alt',entries[0]['notes'])

    def test_packaged_history_contains_current_and_previous_notes(self):
        entries=release_history()
        self.assertEqual(entries[0]['version'],APP_VERSION)
        self.assertIn('3.7.0',{entry['version'] for entry in entries})
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/'CHANGELOG.md').read_text(encoding='utf-8'),(root/'app/creality-cfs-writer/app-release-history.md').read_text(encoding='utf-8'))

    def test_links_keep_their_destination_without_markdown_markup(self):
        self.assertEqual(note_blocks('Details: [Projekt](https://example.org/project).'),[('body','Details: Projekt (https://example.org/project).')])
