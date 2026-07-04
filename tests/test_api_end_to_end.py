"""End-to-end API tests: real HTTP server on an ephemeral port, real
SQLite database in a temp folder, real urllib client."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "client"))

import api  # noqa: E402
import db as dbmod  # noqa: E402
import server as servermod  # noqa: E402


class ApiEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="workbay-test-")
        cls.db_path = os.path.join(cls.tmp, "workbay.db")
        database = dbmod.Database(cls.db_path)
        cls.httpd = servermod.make_server("127.0.0.1", 0, database)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(
            target=cls.httpd.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def client(self):
        return api.ApiClient(f"127.0.0.1:{self.port}")

    # ----------------------------------------------------------- tests

    def test_00_ping(self):
        self.assertTrue(self.client().ping(retry=False)["ok"])

    def test_01_default_admin_seeded(self):
        client = self.client()
        result = client.login("admin", "admin123")
        self.assertEqual(result["user"]["role"], "admin")

    def test_02_bad_login_rejected(self):
        client = self.client()
        with self.assertRaises(api.ApiRequestError) as ctx:
            client.login("admin", "wrong")
        self.assertEqual(ctx.exception.status, 401)

    def test_03_full_workshop_flow_with_exact_totals(self):
        client = self.client()
        client.register("Benoni Motors", "benoni", "pass1234")
        workshop_id = client.user["workshop_id"]

        # Settings: labour rate R450/h
        workshop = client.update_workshop(
            workshop_id, labour_rate_cents=45000
        )
        self.assertEqual(workshop["labour_rate_cents"], 45000)

        # Book in AB12 CDE with split repair items
        vehicle = client.create_vehicle({
            "registration": "ab12 cde",
            "year": "2019",
            "make": "VW Polo",
            "customer": "S. Nkosi",
            "phone": "082 123 4567",
            "labour_hours": "2",
            "job": "brake pads, oil change",
        })
        self.assertEqual(vehicle["registration"], "AB12 CDE")
        self.assertEqual(
            [i["description"] for i in vehicle["items"]],
            ["Brake pads", "Oil change"],
        )
        self.assertEqual(vehicle["job"], "Brake pads, Oil change")

        # Part CK500 Clutch kit R1,000 at 10%
        vehicle = client.add_part(vehicle["id"], {
            "part_number": "CK500", "name": "Clutch kit",
            "supplier": "Midas", "cost_cents": 100000,
            "discount_pct": 10, "status": "Ordered",
        })
        import theme

        t = theme.vehicle_totals(
            vehicle["parts"], vehicle["labour_hours"],
            vehicle["labour_rate_cents"],
        )
        self.assertEqual(theme.format_money(t["total"]), "R2,070.00")

        # 3 hours -> R2,587.50
        vehicle = client.update_vehicle(vehicle["id"], labour_hours=3)
        t = theme.vehicle_totals(
            vehicle["parts"], vehicle["labour_hours"],
            vehicle["labour_rate_cents"],
        )
        self.assertEqual(theme.format_money(t["total"]), "R2,587.50")

        # back to 2h, part cost R1,200 -> R2,277.00
        vehicle = client.update_vehicle(vehicle["id"], labour_hours=2)
        part_id = vehicle["parts"][0]["id"]
        vehicle = client.update_part(part_id, cost_cents=120000)
        t = theme.vehicle_totals(
            vehicle["parts"], vehicle["labour_hours"],
            vehicle["labour_rate_cents"],
        )
        self.assertEqual(theme.format_money(t["total"]), "R2,277.00")

        # tick off an item; add more items via the split
        item_id = vehicle["items"][0]["id"]
        vehicle = client.set_item_done(item_id, True)
        self.assertEqual(vehicle["items"][0]["done"], 1)
        vehicle = client.add_items(
            vehicle["id"], "wheel alignment; new wipers"
        )
        self.assertEqual(
            [i["description"] for i in vehicle["items"]],
            ["Brake pads", "Oil change", "Wheel alignment", "New wipers"],
        )
        self.assertIn("Wheel alignment", vehicle["job"])

        # part status cycle
        part_id = vehicle["parts"][0]["id"]
        vehicle = client.update_part(part_id, status="Arrived")
        self.assertEqual(vehicle["parts"][0]["status"], "Arrived")
        vehicle = client.update_part(part_id, status="Fitted")
        self.assertEqual(vehicle["parts"][0]["status"], "Fitted")

        # history search by partial registration
        found = client.list_vehicles(scope="all", query="AB12")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["registration"], "AB12 CDE")
        # ...and by job text
        found = client.list_vehicles(scope="all", query="wipers")
        self.assertEqual(len(found), 1)
        # ...and no false positives
        self.assertEqual(
            client.list_vehicles(scope="all", query="ZZ99"), []
        )

    def test_04_workshop_isolation_and_admin_access(self):
        one = self.client()
        one.register("Shop One", "shopone", "pass1234")
        vehicle = one.create_vehicle({"registration": "ONE 111"})

        two = self.client()
        two.register("Shop Two", "shoptwo", "pass1234")
        # other workshop cannot see or touch it
        self.assertEqual(
            [v["registration"] for v in two.list_vehicles(scope="all")],
            [],
        )
        with self.assertRaises(api.ApiRequestError) as ctx:
            two.get_vehicle(vehicle["id"])
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(api.ApiRequestError):
            two.update_workshop(
                one.user["workshop_id"], labour_rate_cents=1
            )

        # admin sees everything and can edit the labour rate
        admin = self.client()
        admin.login("admin", "admin123")
        registrations = [
            v["registration"] for v in admin.list_vehicles(scope="all")
        ]
        self.assertIn("ONE 111", registrations)
        workshops = admin.list_workshops()
        self.assertIn("Shop One", [w["name"] for w in workshops])
        admin.update_workshop(
            one.user["workshop_id"], labour_rate_cents=50000
        )
        self.assertEqual(
            one.get_workshop(one.user["workshop_id"])["labour_rate_cents"],
            50000,
        )

        # non-admin cannot list workshops
        with self.assertRaises(api.ApiRequestError) as ctx:
            one.list_workshops()
        self.assertEqual(ctx.exception.status, 403)

    def test_05_unauthenticated_rejected(self):
        client = self.client()
        with self.assertRaises(api.ApiRequestError) as ctx:
            client.list_vehicles()
        self.assertEqual(ctx.exception.status, 401)

    def test_06_validation_errors(self):
        client = self.client()
        client.register("Validation Shop", "valshop", "pass1234")
        with self.assertRaises(api.ApiRequestError):
            client.create_vehicle({"registration": ""})
        with self.assertRaises(api.ApiRequestError):
            client.create_vehicle({"registration": "X", "year": "banana"})
        with self.assertRaises(api.ApiRequestError):
            client.create_vehicle({"registration": "X", "labour_hours": "-2"})
        vehicle = client.create_vehicle({"registration": "VAL 123"})
        with self.assertRaises(api.ApiRequestError):
            client.add_part(vehicle["id"], {"cost_cents": -5})
        with self.assertRaises(api.ApiRequestError):
            client.add_part(vehicle["id"], {"discount_pct": 150})
        with self.assertRaises(api.ApiRequestError):
            client.add_part(vehicle["id"], {"status": "Lost"})
        # duplicate username
        dup = self.client()
        with self.assertRaises(api.ApiRequestError) as ctx:
            dup.register("Another Shop", "valshop", "pass1234")
        self.assertEqual(ctx.exception.status, 409)

    def test_07_persistence_across_server_restart(self):
        """Data must survive a full server stop/start (fresh Database on
        the same file) -- the close-and-reopen-the-app scenario."""
        client = self.client()
        client.register("Persist Shop", "persist", "pass1234")
        client.update_workshop(
            client.user["workshop_id"], labour_rate_cents=45000
        )
        vehicle = client.create_vehicle({
            "registration": "PER 517", "job": "cambelt", "labour_hours": 1,
        })
        client.add_part(vehicle["id"], {
            "part_number": "CB1", "name": "Cambelt", "cost_cents": 50000,
        })

        # restart: new server + new Database object on the same file
        db_path = os.path.join(self.tmp, "workbay.db")
        httpd2 = servermod.make_server(
            "127.0.0.1", 0, dbmod.Database(db_path)
        )
        port2 = httpd2.server_address[1]
        thread = threading.Thread(target=httpd2.serve_forever, daemon=True)
        thread.start()
        try:
            fresh = api.ApiClient(f"127.0.0.1:{port2}")
            # session tokens are memory-only: must log in again
            with self.assertRaises(api.ApiRequestError):
                fresh.token = client.token
                fresh.list_vehicles()
            fresh.token = None
            fresh.login("persist", "pass1234")
            vehicles = fresh.list_vehicles(scope="all", query="PER 517")
            self.assertEqual(len(vehicles), 1)
            reloaded = fresh.get_vehicle(vehicles[0]["id"])
            self.assertEqual(reloaded["parts"][0]["name"], "Cambelt")
            self.assertEqual(reloaded["labour_rate_cents"], 45000)
            self.assertEqual(
                [i["description"] for i in reloaded["items"]], ["Cambelt"]
            )
        finally:
            httpd2.shutdown()
            httpd2.server_close()

    def test_08_change_password(self):
        client = self.client()
        client.register("PW Shop", "pwshop", "oldpass")
        with self.assertRaises(api.ApiRequestError):
            client.change_password("wrong", "newpass")
        client.change_password("oldpass", "newpass")
        fresh = self.client()
        with self.assertRaises(api.ApiRequestError):
            fresh.login("pwshop", "oldpass")
        fresh.login("pwshop", "newpass")

    def test_09_delete_cascade(self):
        client = self.client()
        client.register("Delete Shop", "delshop", "pass1234")
        vehicle = client.create_vehicle({
            "registration": "DEL 001", "job": "a, b",
        })
        client.add_part(vehicle["id"], {"name": "Widget"})
        admin = self.client()
        admin.login("admin", "admin123")
        admin.delete_workshop(client.user["workshop_id"])
        with self.assertRaises(api.ApiRequestError) as ctx:
            admin.get_vehicle(vehicle["id"])
        self.assertEqual(ctx.exception.status, 404)
        # user is gone too
        with self.assertRaises(api.ApiRequestError):
            self.client().login("delshop", "pass1234")

    def test_10_split_items(self):
        self.assertEqual(
            dbmod.split_items("brake pads, oil change; wheel alignment"),
            ["Brake pads", "Oil change", "Wheel alignment"],
        )
        self.assertEqual(
            dbmod.split_items("one\ntwo\n\n , ;"), ["One", "Two"]
        )
        self.assertEqual(dbmod.split_items(""), [])


if __name__ == "__main__":
    unittest.main()
