import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tvdata_api import BuildError, build

class ApiBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "_site"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def fixture(self):
        self.write("tables/TV-L/Meta.csv", "name,value\npay_grad_name,E\nvalid_from,2025.02.01\nname_de,Entgelttabelle TV-L\nallowances,annual;vwl\nprv,vbl-west\n")
        self.write("tables/TV-L/Table.csv", "T,1,4(a),4b,5\n14,4945.50,6222.99,,6924.48\n")
        self.write("tables/TV-L/Adv.csv", "T,1,4(a),4b,5\n14,1,4,,5\n")
        self.write("tables/Beamte-LSA-A/Meta.csv", "key,value\npay_grad_name,A\nvalid_from,2025.02.01\nname_de,Landesbesoldungsordnung A Sachsen-Anhalt\n")
        self.write("tables/Beamte-LSA-A/Table.csv", "T,1,2\n14,5056.74,5356.22\n")
        self.write("tables/Beamte-LSA-A/Adv.csv", "T,1,2\n14,2,3\n")
        self.write("allowances/annual/Meta.csv", "name,value\nlabel_de,Jahressonderzahlung\noptions,no;yes\n")
        self.write("allowances/annual/Table.csv", "T,no,yes\n14,0,4.1667\n")
        self.write("prv/vbl-west/Meta.csv", "name,value,comment\nlabel_de,VBL-West,\narbeitnehmeranteil,1.81,\n")
        self.write("api/index.html", "<h1>TVData API</h1>")

    def test_builds_all_resources(self):
        self.fixture()
        result = build(self.root, self.out, "owner/repo", "abc123")
        self.assertEqual(result["counts"]["tables"], 2)
        self.assertEqual(result["counts"]["civil_service_tables"], 1)
        self.assertTrue((self.out / "v1/openapi.json").exists())
        self.assertTrue((self.out / "v1/values.csv").exists())
        self.assertTrue((self.out / "v1/schemas/table.schema.json").exists())
        self.assertTrue((self.out / "index.html").exists())
        table = json.loads((self.out / "v1/tables/tv-l.json").read_text())
        self.assertEqual(table["columns"], ["1", "4(a)", "4b", "5"])
        self.assertEqual(table["grades"][0]["steps"]["5"], 6924.48)
        civil = json.loads((self.out / "v1/tables/beamte-lsa-a.json").read_text())
        self.assertEqual(civil["kind"], "civil_service")

    def test_duplicate_leaf_names_use_path_ids(self):
        for parent in ("Tarife", "Besoldung"):
            self.write(f"tables/{parent}/Shared/Meta.csv", f"name,value\nname_de,{parent}\n")
            self.write(f"tables/{parent}/Shared/Table.csv", "T,1\n1,100\n")
        build(self.root, self.out)
        index = json.loads((self.out / "v1/tables/index.json").read_text())
        self.assertEqual({x["id"] for x in index["items"]}, {"tarife-shared", "besoldung-shared"})

    def test_invalid_meta_is_actionable(self):
        self.write("tables/Broken/Meta.csv", "name,wrong\nname_de,Broken\n")
        self.write("tables/Broken/Table.csv", "T,1\n1,100\n")
        with self.assertRaises(BuildError) as error:
            build(self.root, self.out)
        self.assertIn("requires a 'value' column", str(error.exception))

if __name__ == "__main__":
    unittest.main()
