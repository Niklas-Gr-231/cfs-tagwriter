# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from copy import deepcopy
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/creality-cfs-writer'))
from cfs_slicer_sync_ui import group_rows

class ResultGroups(unittest.TestCase):
 def row(self,action,name='Example'):
  return {'action':action,'identity':action,'name':name,'material_id':'99001'}
 def test_authoritative_plan_separates_new_changes_and_current(self):
  actions=('copy_created','copy_restored','copy_updated','slicer_cloud_updated','copy_unchanged','slicer_cloud_unchanged')
  plan=[self.row(action) for action in actions];before=deepcopy(plan);groups=group_rows(plan)
  self.assertEqual([r['action'] for r in groups['new']],['copy_created','copy_restored'])
  self.assertEqual({r['action'] for r in groups['updated']},{'copy_updated','slicer_cloud_updated'})
  self.assertEqual({r['action'] for r in groups['unchanged']},{'copy_unchanged','slicer_cloud_unchanged'})
  self.assertEqual(plan,before)
 def test_unrecognized_actions_are_never_reported_as_unchanged(self):
  groups=group_rows([self.row('future_policy_change')]);self.assertEqual(len(groups['updated']),1);self.assertFalse(groups['unchanged'])
 def test_each_group_has_stable_case_insensitive_name_order(self):
  groups=group_rows([self.row('copy_created','Zulu'),dict(self.row('copy_created','alpha'),identity='second')])
  self.assertEqual([r['name'] for r in groups['new']],['alpha','Zulu'])

if __name__=='__main__':unittest.main()
