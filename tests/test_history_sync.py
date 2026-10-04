import sys,json,tempfile,unittest,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sync_details import sync
PROJECT_URL = 'https://example.invalid'
class HistoryTests(unittest.TestCase):
 def test_old_finished_history_drains_in_batches_and_is_not_pruned(self):
  rows=[{'id':i,'car_id':1,'started_at':'2026-01-01T00:00:00Z','ended_at':'2026-01-01T00:10:00Z','distance_km':5,'positions':[]} for i in range(1,13)]
  def source(query):
   if 'SELECT id FROM drives' in query:return [{'id':r['id']} for r in rows]
   ids=re.search(r'd.id IN \((.*?)\)',query).group(1)
   selected=[int(i) for i in ids.split(',') if i!='NULL']
   return [r for r in rows if r['id'] in selected]
  config={'url':PROJECT_URL,'owner_id':'00000000-0000-0000-0000-000000000001'}
  with tempfile.TemporaryDirectory() as folder:
   published=[]
   publish=lambda c,t,rs,k: published.extend(rs) if t=='app_drive_details' else None
   results=[sync(config,Path(folder),source,publish,history=True) for _ in range(4)]
   self.assertEqual([r['published'] for r in results],[5,5,2,0])
   self.assertEqual([r['history_pending'] for r in results],[7,2,0,0])
   self.assertEqual(len(json.loads((Path(folder)/'details-manifest.json').read_text())['versions']),12)
   self.assertEqual(len(published),12)
if __name__=='__main__':unittest.main()
