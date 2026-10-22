"""Offline tests: real native PPTX edits plus explicitly simulated CLI responses."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_model_fit import app
from task_model_fit import codex_bridge as bridge
from task_model_fit import slide_tools as slides

FIXTURE = app.ROOT / "assets/baseline.pptx"


class NativeSlideTests(unittest.TestCase):
    def test_all_prepared_edits_preserve_original_and_unrelated_package_parts(self):
        original_hash = slides.digest(FIXTURE)
        before = slides.inspect(FIXTURE)
        with tempfile.TemporaryDirectory() as directory:
            for task in app.TASKS:
                with self.subTest(task=task):
                    destination = Path(directory) / (task + ".pptx")
                    slides.apply(FIXTURE, destination, slides.tool_test_plan(task, before)["operations"][0])
                    self.assertTrue(slides.audit(before, slides.inspect(destination), task)["passed"])
                    with zipfile.ZipFile(FIXTURE) as a, zipfile.ZipFile(destination) as b:
                        self.assertEqual(set(a.namelist()), set(b.namelist()))
                        for name in a.namelist():
                            if name != slides.SLIDE:
                                self.assertEqual(a.read(name), b.read(name), name)
            self.assertEqual(slides.digest(FIXTURE), original_hash)

    def test_audit_detects_wrong_outcome_and_collateral_changes(self):
        before = slides.inspect(FIXTURE)
        after = copy.deepcopy(before)
        after["background"] = "#4A5054"
        after["shapes"][0]["text"] = "Wrong title"
        outcome = slides.audit(before, after, "background")
        self.assertFalse(outcome["passed"])
        self.assertTrue(outcome["checks"][0]["passed"])
        self.assertFalse(outcome["checks"][1]["passed"])
        self.assertFalse(slides.audit(before, before, "background")["passed"])

    def test_unsafe_geometry_and_unknown_operations_are_rejected(self):
        state = slides.inspect(FIXTURE)
        with tempfile.TemporaryDirectory() as directory:
            operation = slides.tool_test_plan("overlap", state)["operations"][0]
            for x in (-5, float("nan"), 5000):
                with self.assertRaises(ValueError):
                    slides.apply(FIXTURE, Path(directory) / "out.pptx", dict(operation, x=x))
            with self.assertRaises(ValueError):
                slides.apply(FIXTURE, Path(directory) / "out.pptx", {"op": "run_shell"})


FAKE_CLI = '''\
#!{python}
import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
scenario=os.environ.get('SLIDE_TEST_SCENARIO','ok')
if args==['--version']:
    print('codex-cli 0.163.0')
elif args==['login','status']:
    if scenario=='runtime':
        print('Error loading configuration: no /proc/self/exe available',file=sys.stderr);sys.exit(1)
    if scenario=='api':
        print('Logged in using an API key: sk-PRIVATE');sys.exit(0)
    print('Logged in using ChatGPT')
else:
    assert not any(k in os.environ for k in ['OPENAI_API_KEY','CODEX_API_KEY','CODEX_ACCESS_TOKEN'])
    capture=os.environ.get('SLIDE_TEST_CAPTURE')
    if capture: Path(capture).write_text(json.dumps(args))
    if scenario=='timeout':time.sleep(5)
    print(json.dumps({{'type':'thread.started','thread_id':'PRIVATE_ID'}}),flush=True)
    if scenario=='rejected':
        print(json.dumps({{'type':'turn.failed','error':{{'message':'model is not supported PRIVATE_DETAIL'}}}}),flush=True);sys.exit(1)
    operation={{'op':'set_background','shape_id':None,'x':None,'y':None,'width':None,'height':None,'color':'#4A5054','text':None}}
    plan={{'operations':[operation],'note':'Changed the background.'}}
    if scenario=='invalid':plan={{'unexpected':'PRIVATE_RESPONSE'}}
    if scenario=='tool':print(json.dumps({{'type':'item.completed','item':{{'type':'command_execution','command':'PRIVATE_COMMAND'}}}}),flush=True)
    print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':json.dumps(plan)}}}}),flush=True)
    print(json.dumps({{'type':'turn.completed','usage':{{'input_tokens':20,'output_tokens':10,'private':'PRIVATE_USAGE'}}}}),flush=True)
    print('ERROR codex_memories_write::phase2: Phase 2 no changes',file=sys.stderr)
'''


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.binary = self.directory / "fake-codex"
        self.binary.write_text(FAKE_CLI.format(python=sys.executable))
        self.binary.chmod(0o700)
        self.capture = self.directory / "args.json"
        self.env = patch.dict(os.environ, {"SLIDE_TEST_SCENARIO": "ok", "SLIDE_TEST_CAPTURE": str(self.capture),
            "OPENAI_API_KEY": "sk-PRIVATE", "CODEX_API_KEY": "PRIVATE", "CODEX_ACCESS_TOKEN": "PRIVATE"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def request(self, model=bridge.MODEL, timeout=5):
        return bridge.request(str(self.binary), app.TASKS["background"]["prompt"], slides.inspect(FIXTURE),
                              self.directory, lambda *_a, **_k: None, threading.Event(), timeout=timeout, model=model)

    def test_native_auth_mode_and_runtime_failure_are_distinguished(self):
        self.assertTrue(bridge.connection(str(self.binary))["ready"])
        os.environ["SLIDE_TEST_SCENARIO"] = "api"
        self.assertFalse(bridge.connection(str(self.binary))["ready"])
        os.environ["SLIDE_TEST_SCENARIO"] = "runtime"
        result = bridge.connection(str(self.binary))
        self.assertEqual(result["category"], "host_runtime_unsupported")
        self.assertEqual(result["authentication"], "unknown")

    def test_both_exact_models_settings_and_usage_are_preserved(self):
        for model, configuration in bridge.MODELS.items():
            plan, metrics = self.request(model)
            args = json.loads(self.capture.read_text())
            self.assertEqual(args[args.index("--model") + 1], model)
            self.assertIn(f'model_reasoning_effort="{configuration["effort"]}"', args)
            self.assertEqual(metrics["requested_model"], model)
            self.assertEqual(metrics["usage"], {"input_tokens": 20, "output_tokens": 10})
            self.assertEqual(plan["operations"][0]["op"], "set_background")
            self.assertIsNone(metrics["provider_compute_seconds"])
            self.assertIsNone(metrics["effective_model"])
            self.assertIn("cli_warning", metrics)
            self.assertNotIn("PRIVATE", json.dumps(metrics))

    def test_rejection_bad_schema_tools_and_timeout_do_not_become_edits(self):
        for scenario, expected in (("rejected", "model_unavailable"), ("invalid", "invalid_structured_response"),
                                   ("tool", "unexpected_model_tool_use"), ("timeout", "request_timeout")):
            with self.subTest(scenario=scenario):
                os.environ["SLIDE_TEST_SCENARIO"] = scenario
                with self.assertRaises(bridge.ModelError) as raised:
                    self.request(timeout=.2 if scenario == "timeout" else 5)
                self.assertEqual(raised.exception.category, expected)
                self.assertNotIn("PRIVATE", str(raised.exception))
                self.assertIsNotNone(raised.exception.metrics.get("elapsed_request_seconds"))

    def test_app_runs_full_structured_path_with_simulated_cli(self):
        lab = app.Lab(self.directory / "data", str(self.binary))
        key = lab.start("background", "gpt-6.1-sol", lab.original, "live")
        deadline = time.monotonic() + 5
        while lab.get_run(key)["status"] == "running" and time.monotonic() < deadline:
            time.sleep(.01)
        run = lab.get_run(key)
        self.assertEqual(run["status"], "completed")
        self.assertTrue(run["audit"]["passed"])
        self.assertEqual(slides.inspect(lab.runs_dir / key / "after.pptx")["background"], "#4A5054")
        self.assertEqual(lab.state(lab.original)["slide"]["background"], "#000000")
        self.assertTrue((lab.runs_dir / key / "run.json").is_file())


class HTTPTests(unittest.TestCase):
    def test_local_web_app_edits_real_file_and_requires_session_header(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = app.Lab(directory)
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            server.lab = lab
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def get(path, data=None):
                headers = {"X-Slide-Lab-Token": lab.token, "Content-Type": "application/json"}
                request = Request(base + path, headers=headers, data=json.dumps(data).encode() if data else None)
                with urlopen(request, timeout=5) as response:
                    return json.load(response)
            try:
                with urlopen(base) as response:
                    self.assertIn(lab.token, response.read().decode())
                with self.assertRaises(HTTPError) as raised:
                    urlopen(base + "/api/bootstrap")
                self.assertEqual(raised.exception.code, 403)
                self.assertEqual(get("/api/bootstrap")["original"]["id"], lab.original)
                key = get("/api/run", {"mode": "tools", "model": "gpt-6-luna", "task": "background", "baseline": lab.original})["id"]
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = get("/api/runs/" + key)
                    if result["status"] != "running": break
                    time.sleep(.01)
                self.assertEqual(result["status"], "completed")
                self.assertTrue(result["audit"]["passed"])
                self.assertIsNone(result["model"])
                self.assertIsNone(result["metrics"]["elapsed_request_seconds"])
                with urlopen(base + f'/files/snapshots/{result["after"]}.pptx') as response:
                    self.assertTrue(response.read().startswith(b"PK"))
                restored = app.Lab(directory)
                self.assertEqual(restored.get_run(key)["status"], "completed")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
