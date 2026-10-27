"""Feature tests of the generated agents, orchestrator and tool stubs (C7).

Fixtures are SYNTHETIC. The Precord has no sample_data rows, so every case is built from the declared reads of each
action and marked synthetic. That absence is recorded as a gap in the report.
Each test names the required item it covers in a comment above it.
"""
import importlib
import socket
import unittest
from unittest.mock import patch

from agents import blk_01, blk_01_1, blk_01_2, blk_02
from orchestrator import orchestrator

SYNTHETIC = "synthetic"


def intake_case():
    """SYNTHETIC case: the reads of ACT_01 to ACT_04, valid."""
    return {
        "Full Name": "Synthetic Person",
        "Mobile Number": "9000000001",
        "Email": "synthetic@example.invalid",
        "RM Business Code": "RM-SYN",
        "PAN Number": "SYNPAN0000",
        "Aadhaar Number": "000000000000",
        "CKYC Number": "00000000000000",
        "Name": "Synthetic Person",
        "Gender": "F",
        "Date of Birth": "1990-01-01",
        "Address": "1 Synthetic Road",
        "Pincode": "560001",
        "IFSC Code": "SYNT0000001",
        "Bank Account Number": "000111222333",
        "Name As In Bank Account": "Synthetic Person",
    }


def document_case():
    """SYNTHETIC case: all six document slots uploaded, plus the reads of ACT_07."""
    slots = {name: {"filename": name.lower().replace(" ", "_") + ".pdf", "size_bytes": 1024}
             for name in blk_02._READS["ACT_05"]}
    return {
        **slots,
        "Application Status": "QC Pending",
        "Uploaded Documents": dict(slots),
        "KYC Verification Results": {"status": "sample"},
    }


class IntakeRuleTests(unittest.TestCase):
    # BR-ACT_01
    def test_br_act_01_refuses_bad_email_and_blank_mobile(self):
        case = intake_case()
        blk_01.enforce_br_act_01(case)
        with self.assertRaises(blk_01.GuardrailRefusal) as raised:
            blk_01.enforce_br_act_01({**case, "Email": "not-an-email"})
        self.assertEqual(raised.exception.rule_id, "BR-ACT_01")
        with self.assertRaises(blk_01.GuardrailRefusal):
            blk_01.enforce_br_act_01({**case, "Mobile Number": " "})

    # BR-ACT_01
    def test_br_act_01_refusal_stops_the_write_to_the_tool(self):
        case = intake_case()
        case["Email"] = "bad"
        with patch("integrations.tool_01.invoke") as tool:
            with self.assertRaises(blk_01.GuardrailRefusal):
                blk_01.act_01_extract_validate_intake(case)
        self.assertEqual(tool.call_count, 0)

    # BR-ACT_02
    def test_br_act_02_refuses_a_missing_kyc_response(self):
        blk_01.enforce_br_act_02({"KYC verification status": "queued"})
        with self.assertRaises(blk_01.GuardrailRefusal) as raised:
            blk_01.enforce_br_act_02({"KYC verification status": None})
        self.assertEqual(raised.exception.rule_id, "BR-ACT_02")

    # BR-ACT_02
    def test_br_act_02_refuses_when_the_tool_returns_no_status(self):
        with patch("integrations.tool_02.invoke", return_value={}):
            with self.assertRaises(blk_01.GuardrailRefusal):
                blk_01.act_02_orchestrate_kyc_verification(intake_case())

    # BR-ACT_03
    def test_br_act_03_refuses_a_malformed_pincode(self):
        blk_01.enforce_br_act_03({"Pincode": "560001"})
        for bad in ("56001", "ABCDEF", "", None, "060001"):
            with self.subTest(pincode=bad):
                with self.assertRaises(blk_01.GuardrailRefusal) as raised:
                    blk_01.enforce_br_act_03({"Pincode": bad})
                self.assertEqual(raised.exception.rule_id, "BR-ACT_03")

    # BR-ACT_04
    def test_br_act_04_refuses_a_bad_ifsc_and_a_blank_returned_status(self):
        blk_01.enforce_br_act_04({"IFSC Code": "HDFC0001234"})
        with self.assertRaises(blk_01.GuardrailRefusal) as raised:
            blk_01.enforce_br_act_04({"IFSC Code": "HDFC1001234"})
        self.assertEqual(raised.exception.rule_id, "BR-ACT_04")
        with self.assertRaises(blk_01.GuardrailRefusal):
            blk_01.enforce_br_act_04({"IFSC Code": "HDFC0001234", "Bank verification status": ""})

    # BR-ACT_04
    def test_br_act_04_guardrails_map_names_a_callable_enforcer(self):
        for rule_id in ("BR-ACT_01", "BR-ACT_02", "BR-ACT_03", "BR-ACT_04"):
            entry = blk_01.GUARDRAILS[rule_id]
            self.assertEqual(entry["status"], "enforced")
            self.assertTrue(callable(getattr(blk_01, entry["enforced_by"])))


class DocumentRuleTests(unittest.TestCase):
    # BR-ACT_05
    def test_br_act_05_refuses_missing_extension_empty_size_and_no_document(self):
        blk_02.enforce_br_act_05(document_case())
        bad = document_case()
        bad["PAN Card"] = {"filename": "pan", "size_bytes": 10}
        with self.assertRaises(blk_02.GuardrailRefusal) as raised:
            blk_02.enforce_br_act_05(bad)
        self.assertEqual(raised.exception.rule_id, "BR-ACT_05")
        empty = document_case()
        empty["PAN Card"] = {"filename": "pan.pdf", "size_bytes": 0}
        with self.assertRaises(blk_02.GuardrailRefusal):
            blk_02.enforce_br_act_05(empty)
        with self.assertRaises(blk_02.GuardrailRefusal):
            blk_02.enforce_br_act_05({})

    # BR-ACT_05
    def test_br_act_05_applies_the_declared_limits_when_they_are_set(self):
        case = document_case()
        with patch.object(blk_02, "PERMITTED_EXTENSIONS", ("png",)):
            with self.assertRaises(blk_02.GuardrailRefusal):
                blk_02.enforce_br_act_05(case)
        with patch.object(blk_02, "MAX_FILE_SIZE_BYTES", 100):
            with self.assertRaises(blk_02.GuardrailRefusal):
                blk_02.enforce_br_act_05(case)

    # BR-ACT_05
    def test_br_act_05_refusal_stops_the_tool_call(self):
        with patch("integrations.tool_03.invoke") as tool:
            with self.assertRaises(blk_02.GuardrailRefusal):
                blk_02.classify_and_validate_documents_action({"PAN Card": {"filename": "x", "size_bytes": 5}})
        self.assertEqual(tool.call_count, 0)

    # BR-ACT_07
    def test_br_act_07_refuses_incomplete_verification_inputs(self):
        blk_02.enforce_br_act_07(document_case())
        for field in blk_02._READS["ACT_07"]:
            with self.subTest(missing=field):
                case = document_case()
                del case[field]
                with self.assertRaises(blk_02.GuardrailRefusal) as raised:
                    blk_02.enforce_br_act_07(case)
                self.assertEqual(raised.exception.rule_id, "BR-ACT_07")


class GuardrailTests(unittest.TestCase):
    MODULES = (blk_01, blk_01_1, blk_01_2, blk_02)

    # GR-01
    def test_gr_01_refuses_a_tool_the_agent_does_not_declare(self):
        for module in (blk_01, blk_01_1, blk_02):
            with self.subTest(agent=module.AGENT_ID):
                with self.assertRaises(module.GuardrailRefusal):
                    module.enforce_gr_01({}, tool_id="TOOL_99")
        # BLK_01.2 takes tool_ids and declares TOOL_01 only; BLK_02 declares TOOL_03 only.
        with self.assertRaises(blk_01_2.GuardrailRefusal):
            blk_01_2.enforce_gr_01({}, tool_ids=["TOOL_99"])
        with self.assertRaises(blk_01_2.GuardrailRefusal):
            blk_01_2.enforce_gr_01({}, tool_ids=["TOOL_02"])
        blk_01_2.enforce_gr_01({}, tool_ids=["TOOL_01"])
        with self.assertRaises(blk_02.GuardrailRefusal):
            blk_02.enforce_gr_01({}, tool_id="TOOL_01")
        blk_02.enforce_gr_01({}, tool_id="TOOL_03")

    # GR-01
    def test_gr_01_refuses_the_write_through_an_undeclared_tool_binding(self):
        with patch("integrations.tool_03.invoke") as tool:
            with self.assertRaises(blk_01.GuardrailRefusal) as raised:
                blk_01._call_tool("TOOL_03", {}, "S1")
        self.assertEqual(raised.exception.rule_id, "GR-01")
        self.assertEqual(tool.call_count, 0)

    # GR-02
    def test_gr_02_refuses_person_steps(self):
        for module in self.MODULES:
            for step in ("S6", "S8"):
                with self.subTest(agent=module.AGENT_ID, step=step):
                    with self.assertRaises(module.GuardrailRefusal) as raised:
                        module.enforce_gr_02({}, step_id=step)
                    self.assertEqual(raised.exception.rule_id, "GR-02")
        self.assertFalse(blk_01.allowed_step("S6"))
        self.assertTrue(blk_01.allowed_step("S3"))
        self.assertFalse(blk_02.allowed_step("S6"))

    # GR-03
    def test_gr_03_refuses_output_while_a_blocking_rule_is_unmet(self):
        with self.assertRaises(blk_01_1.GuardrailRefusal) as raised:
            blk_01_1.enforce_gr_03({}, rule_violations=["BR-ACT_01"])
        self.assertEqual(raised.exception.rule_id, "GR-03")
        with self.assertRaises(blk_02.GuardrailRefusal):
            blk_02.enforce_gr_03(document_case(), "ACT_05", {"Surprise": 1})
        with self.assertRaises(blk_02.GuardrailRefusal):
            blk_02.enforce_gr_03({}, "ACT_07")

    # GR-03
    def test_gr_03_refuses_an_action_whose_rule_has_no_enforcer(self):
        with patch.dict(blk_01.GUARDRAILS, {"BR-ACT_01": {"status": "enforced", "enforced_by": "nope"}}):
            with self.assertRaises(blk_01.GuardrailRefusal):
                blk_01.enforce_gr_03({}, "ACT_01")

    # GR-04
    def test_gr_04_escalates_when_a_required_field_is_an_open_item(self):
        with patch.object(blk_01, "OPEN_REQUIRED_FIELDS", frozenset({"Pincode"})):
            with self.assertRaises(blk_01.GuardrailRefusal) as raised:
                blk_01.enforce_gr_04({"Pincode": None}, "ACT_03")
            self.assertEqual(raised.exception.rule_id, "GR-04")
            blk_01.enforce_gr_04({"Pincode": "560001"}, "ACT_03")
        with patch.object(blk_01_1, "OPEN_ITEM_FIELDS", ("Address",)):
            with self.assertRaises(blk_01_1.GuardrailRefusal):
                blk_01_1.enforce_gr_04({})
        with patch.object(blk_02, "BLOCKING_OPEN_ITEM_FIELDS", ("Bank Proof",)):
            with self.assertRaises(blk_02.GuardrailRefusal):
                blk_02.enforce_gr_04({}, "ACT_05")


class OrchestrationTests(unittest.TestCase):
    # TRIGGER-BLK_01
    def test_trigger_blk_01_starts_only_on_the_declared_trigger(self):
        self.assertEqual(orchestrator.entry_agent("Inbound channel message"), "BLK_01")
        self.assertEqual([t["starts"] for t in orchestrator.TRIGGERS], ["BLK_01"])
        self.assertEqual(orchestrator.TRIGGERS[0]["channel"], blk_01_trigger_text())
        for other in ("File / object drop", "Schedule", ""):
            with self.assertRaises(KeyError):
                orchestrator.entry_agent(other)
        self.assertEqual(orchestrator.case_route("Inbound channel message"), ["BLK_01", "BLK_02"])

    # EDGE-BLK_01-BLK_02
    def test_edge_blk_01_blk_02_on_done(self):
        self.assertEqual(orchestrator.next_agent("BLK_01", "done"), "BLK_02")
        self.assertIsNone(orchestrator.next_agent("BLK_02", "done"))
        self.assertIsNone(orchestrator.next_agent("BLK_01", "failed"))

    # EDGE-BLK_01-BLK_01.1
    def test_edge_blk_01_blk_01_1_agent_tool(self):
        targets = orchestrator.next_agent("BLK_01", "agent_tool")
        self.assertIsInstance(targets, list)
        self.assertIn("BLK_01.1", targets)

    # EDGE-BLK_01-BLK_01.2
    def test_edge_blk_01_blk_01_2_agent_tool(self):
        targets = orchestrator.next_agent("BLK_01", "agent_tool")
        self.assertIn("BLK_01.2", targets)
        self.assertNotIn("BLK_02", targets)

    # PERSON-S6
    def test_person_s6_is_never_assigned_to_an_agent(self):
        self.assertTrue(orchestrator.is_person_step("S6"))
        self.assertIsNone(orchestrator.agent_for_step("S6"))

    # PERSON-S8
    def test_person_s8_is_never_assigned_to_an_agent(self):
        self.assertTrue(orchestrator.is_person_step("S8"))
        self.assertIsNone(orchestrator.agent_for_step("S8"))
        self.assertEqual(orchestrator.agent_for_step("S7"), "BLK_02")
        self.assertFalse(orchestrator.is_person_step("S1"))
        with self.assertRaises(KeyError):
            orchestrator.owner_of("S99")


def blk_01_trigger_text():
    return "Incoming prospect registration submission"


class ExceptionRouteTests(unittest.TestCase):
    # EXC_01
    def test_exc_01_escalates_a_duplicate_and_resumes_at_act_01(self):
        route = blk_01.handle_exception("EXC_01", "c-1", ValueError("mobile already registered"))
        self.assertEqual(route["escalation_route"], "FLS User / Employee manual resolution queue")
        self.assertEqual(route["resume_from"], "ACT_01")
        self.assertTrue(route["alert"])
        self.assertIn("mobile already registered", route["error"])

    # EXC_01
    def test_exc_01_run_case_routes_a_failed_intake_without_calling_the_tool(self):
        case = intake_case()
        case["Email"] = "bad"
        with patch("integrations.tool_01.invoke") as tool:
            result = blk_01.run_case("c-1", case)
        self.assertEqual(result["outcome"], "routed")
        self.assertEqual(result["route"]["exception_id"], "EXC_01")
        self.assertEqual(result["trace"], [])
        self.assertEqual(tool.call_count, 0)

    # EXC_02
    def test_exc_02_escalates_to_the_retry_queue_and_resumes_at_act_02(self):
        route = blk_01.handle_exception("EXC_02", "c-2", RuntimeError("HTTP 503"))
        self.assertEqual(route["escalation_route"], "Async retry queue / Operations exception handler")
        self.assertEqual(route["resume_from"], "ACT_02")
        self.assertTrue(route["alert"])
        with self.assertRaises(KeyError):
            blk_01.handle_exception("EXC_99", "c-2", RuntimeError("x"))

    # EXC_02
    def test_exc_02_kyc_outage_halts_and_never_bypasses_verification(self):
        with patch("integrations.tool_02.invoke", side_effect=RuntimeError("503 Service Temporarily Unavailable")):
            result = blk_01.run_case("c-2", intake_case())
        self.assertEqual(result["outcome"], "routed")
        self.assertEqual(result["route"]["exception_id"], "EXC_02")
        self.assertEqual(result["route"]["resume_from"], "ACT_02")
        self.assertEqual(result["trace"], ["ACT_01"])
        self.assertNotIn("KYC verification status", result["case"])
        self.assertNotIn("ACT_03", result["trace"])

    # EXC_03
    def test_exc_03_escalates_an_invalid_document_to_the_upload_interface(self):
        route = blk_02.handle_exception("EXC_03", "c-3", ValueError("unreadable"))
        self.assertEqual(route["escalation_route"], "Prospective agent upload interface")
        self.assertEqual(route["resume_from"], "ACT_05")
        self.assertEqual(route["human_work_item"], "Re-upload valid document in required format")

    # EXC_03
    def test_exc_03_run_case_rejects_the_bad_file_and_stops_before_qc(self):
        case = document_case()
        case["Bank Proof"] = {"filename": "proof", "size_bytes": 10}
        with patch("integrations.tool_03.invoke") as tool:
            result = blk_02.run_case("c-3", case)
        self.assertEqual(result["outcome"], "routed")
        self.assertEqual(result["route"]["exception_id"], "EXC_03")
        self.assertEqual(result["trace"], [])
        self.assertEqual(tool.call_count, 0)

    # EXC_05
    def test_exc_05_escalates_a_qc_discrepancy_to_the_reviewer_workbench(self):
        route = blk_02.handle_exception("EXC_05", "c-5", ValueError("mismatch"))
        self.assertEqual(route["escalation_route"], "Operations / QC reviewer workbench")
        self.assertEqual(route["resume_from"], "ACT_07")
        self.assertEqual(route["containment"], "Route case to Operations QC exception list")

    # EXC_05
    def test_exc_05_a_missing_document_slot_raises_the_discrepancy_and_routes(self):
        case = document_case()
        del case["Uploaded Documents"]["Education Document"]
        result = blk_02.run_case("c-5", case)
        self.assertEqual(result["trace"], ["ACT_05"])
        self.assertEqual(result["route"]["exception_id"], "EXC_05")
        self.assertIn("Education Document", " ".join(result["route"]["draft"]["Discrepancy recommendation list"]))
        self.assertIsNone(result["next"])

    # EXC_05
    def test_exc_05_a_clean_draft_completes_and_does_not_approve(self):
        draft = blk_02.draft_qc_review_action(document_case())
        self.assertEqual(draft["Discrepancy recommendation list"], [])
        self.assertTrue(any("does not replace inspection" in line for line in draft["Reviewer remark drafts"]))
        self.assertEqual(blk_02.AUTONOMY, "draft_for_approval")


class FailurePathTests(unittest.TestCase):
    # FAIL-BLK_01
    def test_fail_blk_01_halts_and_flags_for_human_review(self):
        result = blk_01.run_case("c-9", [])  # SYNTHETIC malformed input: not an object
        self.assertEqual(result["outcome"], "routed")
        self.assertEqual(result["trace"], [])
        route = result["route"]
        self.assertEqual(route["status_tag"], "halted_for_human_review")
        self.assertTrue(route["alert"])
        self.assertEqual(route["escalation_route"], "FLS User / Employee manual resolution queue")
        self.assertIn("ValidationError", route["error"])

    # FAIL-BLK_01
    def test_fail_blk_01_sub_agents_degrade_to_human_with_error_context(self):
        for module in (blk_01_1, blk_01_2):
            with self.subTest(agent=module.AGENT_ID):
                result = module.run_case("c-9", {})
                self.assertEqual(result["outcome"], "completed")
                with patch.object(module, "enforce_gr_04", side_effect=ValueError("boom")):
                    result = module.run_case("c-9", {})
                self.assertEqual(result["outcome"], "routed")
                self.assertEqual(result["route"]["status_tag"], "halted_for_human_review")
                self.assertIn("boom", result["route"]["error"])
                self.assertTrue(result["route"]["alert"])

    # FAIL-BLK_01
    def test_fail_blk_01_full_run_completes_when_nothing_fails(self):
        result = blk_01.run_case("c-ok", intake_case())
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["trace"], ["ACT_01", "ACT_02", "ACT_03", "ACT_04"])
        self.assertEqual(result["next"], "ACT_05")
        self.assertIsNone(result["route"])

    # FAIL-BLK_02
    def test_fail_blk_02_flags_unreadable_documents_for_operator_inspection(self):
        route = blk_02.handle_failure("c-8", RuntimeError("unreadable scan"))
        self.assertEqual(route["status_tag"], "flagged_for_human_inspection")
        self.assertEqual(route["escalation_route"], "Operations / QC reviewer queue")
        self.assertTrue(route["alert"])
        self.assertIn("unreadable scan", route["error"])

    # FAIL-BLK_02
    def test_fail_blk_02_guardrail_refusal_emits_an_event_and_routes(self):
        events = []
        with patch.object(blk_02, "emit_event", side_effect=lambda name, case_id, **f: events.append((name, f))):
            result = blk_02.run_case("c-8", {"PAN Card": {"filename": "scan", "size_bytes": 3}})
        self.assertEqual(result["outcome"], "routed")
        self.assertEqual([name for name, _ in events], ["guardrail.triggered"])
        self.assertEqual(events[0][1]["guardrail_event"], "BR-ACT_05")


class StubTests(unittest.TestCase):
    def _assert_stub(self, module_name, payload):
        module = importlib.import_module(module_name)
        with patch.object(socket, "create_connection") as connect, patch.object(socket.socket, "connect") as raw:
            response = module.invoke(payload, "c-stub")
        self.assertIsInstance(response, dict)
        self.assertIs(module.IS_MOCK, True)
        self.assertEqual(connect.call_count + raw.call_count, 0)
        return module, response

    # STUB-TOOL_01
    def test_stub_tool_01_returns_a_mock_response_and_opens_no_connection(self):
        module, response = self._assert_stub("integrations.tool_01", intake_case())
        self.assertEqual(set(response), set(module.RESPONSE_FIELDS))
        self.assertEqual(module.ENDPOINT, "__MOCK__")
        self.assertEqual(module.OPEN_ITEMS, ("HR-201:BLK_01:TOOL_01",))

    # STUB-TOOL_02
    def test_stub_tool_02_returns_a_mock_response_and_opens_no_connection(self):
        module, response = self._assert_stub("integrations.tool_02", {"PAN Number": "SYNPAN0000"})
        self.assertEqual(list(response), ["KYC verification status"])
        self.assertEqual(module.OPEN_ITEMS, ("HR-201:BLK_01:TOOL_02",))

    # STUB-TOOL_03
    def test_stub_tool_03_returns_a_mock_response_and_opens_no_connection(self):
        module, response = self._assert_stub("integrations.tool_03", document_case())
        self.assertEqual(set(response), {"Categorized document slots", "Validation status"})
        self.assertEqual(module.OPEN_ITEMS, ("HR-201:BLK_02:TOOL_03",))

    # STUB-TOOL_01
    def test_stub_responses_are_copies_so_a_caller_cannot_change_the_stub(self):
        module = importlib.import_module("integrations.tool_01")
        first = module.invoke({}, "c-1")
        first["Bank Name"] = "changed"
        self.assertEqual(module.invoke({}, "c-1")["Bank Name"], "sample")


class NotificationTests(unittest.TestCase):
    # EXC_01
    def test_exc_01_notification_masks_mobile_and_pan(self):
        note = blk_01.build_notification("c-1", intake_case())
        self.assertNotIn("9000000001", note["message"])
        self.assertNotIn("SYNPAN0000", note["message"])
        self.assertTrue(note["message"].count("*") >= 6)
        failed = blk_01.build_notification("c-1", intake_case(), channel_failed=True)
        self.assertEqual(failed["channel"], "UI inline error")


if __name__ == "__main__":
    unittest.main()
