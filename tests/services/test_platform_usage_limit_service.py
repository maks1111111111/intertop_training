from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import CompanyRepository
from app.repositories.company_usage_limit_repository import CompanyUsageLimitRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.platform_usage_limit_service import PlatformUsageLimitError, PlatformUsageLimitService
class PlatformUsageLimitServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/"x.db"; initialize_database(self.db); CompanyRepository().create(self.db,"a","A")
  with get_connection(self.db) as c: self.owner=int(c.execute("INSERT INTO users (username) VALUES ('o')").lastrowid)
  self.admins=PlatformAdminRepository(); self.admins.bootstrap_owner(self.db,self.owner); self.s=PlatformUsageLimitService(CompanyUsageLimitRepository(),CompanyRepository(),self.admins)
 def tearDown(self): self.tmp.cleanup()
 def test_owner_sets_limits_and_audits(self):
  limit=self.s.set(self.db,actor_user_id=self.owner,company_id="a",max_active_members=10,max_courses=2,reason="Plan change")
  self.assertEqual((limit.max_active_members,limit.max_courses),(10,2)); self.assertEqual(self.admins.list_audit_events(self.db)[0].action,"company_usage_limits.updated")
 def test_rejects_invalid_limit(self):
  with self.assertRaises(PlatformUsageLimitError): self.s.set(self.db,actor_user_id=self.owner,company_id="a",max_active_members=0,max_courses=None,reason="x")
if __name__=="__main__": unittest.main()
