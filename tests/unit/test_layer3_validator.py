"""Unit tests for Layer 3 — Output Validator."""

import pytest
from guardrails.layer3_output_validator import (
    check_pii,
    check_gst_rates,
    validate_output,
    validate_output_topic,
    validate_output_v2,
)


class TestCheckPii:
    def test_detects_pan(self):
        hits = check_pii("The PAN number is ABCDE1234F for this vendor.")
        types = [h['type'] for h in hits]
        assert 'pan_number' in types

    def test_detects_phone(self):
        hits = check_pii("Call us at 9876543210 for support.")
        types = [h['type'] for h in hits]
        assert 'phone_number' in types

    def test_detects_email(self):
        hits = check_pii("Send invoices to billing@example.com")
        types = [h['type'] for h in hits]
        assert 'email' in types

    def test_clean_erp_response_no_pii(self):
        text = "GST rate on restaurant services is 5%. File GSTR-3B by 20th of next month."
        hits = check_pii(text)
        assert len(hits) == 0


class TestCheckGstRates:
    def test_valid_gst_rate_not_flagged(self):
        text = "GST rate is 18% on IT services."
        errors = check_gst_rates(text)
        assert len(errors) == 0

    def test_invalid_gst_rate_flagged(self):
        text = "GST rate is 22% on this product."
        errors = check_gst_rates(text)
        assert len(errors) == 1
        assert errors[0]['claimed_rate'] == 22.0

    def test_multiple_rates_mixed(self):
        text = "GST rate is 18% here but GST rate is 15% there."
        errors = check_gst_rates(text)
        assert any(e['claimed_rate'] == 15.0 for e in errors)
        assert not any(e['claimed_rate'] == 18.0 for e in errors)


class TestValidateOutput:
    def test_valid_response_passes(self):
        text = "The GST rate on restaurant services is 5% with ITC available. File GSTR-3B monthly."
        result = validate_output(text)
        assert result['valid'] is True
        assert result['issues'] == []

    def test_too_short_flagged(self):
        result = validate_output("ok")
        assert result['valid'] is False
        assert 'output_too_short' in result['issues']

    def test_too_long_flagged(self):
        result = validate_output("word " * 1000)
        assert result['valid'] is False
        assert 'output_too_long' in result['issues']


class TestValidateOutputTopic:
    def test_erp_response_passes(self):
        text = "GST rate on software services is 18%. You need to file GSTR-1 by the 11th."
        result = validate_output_topic(text)
        assert result['is_oos'] is False

    def test_weather_response_flagged(self):
        text = "Today's weather in Delhi is sunny with a temperature of 32 degrees."
        result = validate_output_topic(text)
        assert result['is_oos'] is True

    def test_story_response_flagged(self):
        text = "Once upon a time there was a merchant who sold spices in the market."
        result = validate_output_topic(text)
        assert result['is_oos'] is True


class TestValidateOutputV2:
    def test_clean_response_fully_valid(self):
        text = "GST rate on IT services (SAC 998314) is 18% under CGST+SGST. File GSTR-3B monthly."
        result = validate_output_v2(text)
        assert result['valid'] is True
        assert result['issues'] == []
        assert result['gst_errors'] == []
        assert result['topic']['is_oos'] is False

    def test_invalid_gst_rate_caught(self):
        text = "GST rate is 22% on this product. File GSTR-3B monthly."
        result = validate_output_v2(text)
        assert any('invalid_gst_rate' in i for i in result['issues'])

    def test_oos_response_caught(self):
        text = "Today's weather is sunny and pleasant."
        result = validate_output_v2(text)
        assert any('oos_response' in i for i in result['issues'])


class TestGstRateSet:
    """The valid-rate set follows the structure in force from 22 Sep 2025."""

    def test_current_slabs_are_accepted(self):
        for rate in ("0", "5", "18", "40"):
            assert check_gst_rates(f"The GST rate is {rate}% on this supply.") == []

    def test_cgst_sgst_half_rates_are_accepted(self):
        assert check_gst_rates("CGST 2.5% plus SGST 2.5% applies on a 5% supply.") == []
        assert check_gst_rates("GST 9% CGST and 9% SGST on an 18% supply.") == []
        assert check_gst_rates("Composition tax is 1%: CGST 0.5% and SGST 0.5%.") == []

    def test_abolished_slabs_are_flagged(self):
        for rate in (12, 28):
            errors = check_gst_rates(f"The GST rate is {rate}% on this supply.")
            assert [e['claimed_rate'] for e in errors] == [float(rate)]

    @pytest.mark.parametrize("rate", [10, 13, 15, 22, 35])
    def test_made_up_rates_are_flagged(self, rate):
        assert check_gst_rates(f"The GST rate is {rate}% on this supply.")

    def test_tds_percentage_near_gst_is_not_a_rate(self):
        assert check_gst_rates("TDS under GST is 2% of the payment.") == []

    def test_interest_and_penalty_percentages_are_not_rates(self):
        assert check_gst_rates("Interest under the GST Act is 24% per annum on wrongly availed ITC.") == []
        assert check_gst_rates("GST देर से जमा करने पर 24% ब्याज लगता है।") == []


class TestPiiIsScannedOnce:
    def test_validate_output_v2_runs_check_pii_a_single_time(self, monkeypatch):
        from guardrails import layer3_output_validator as l3
        calls = []
        real = l3.check_pii
        monkeypatch.setattr(l3, 'check_pii', lambda text: calls.append(1) or real(text))
        result = l3.validate_output_v2("GST on software services is 18% under SAC 998314. File GSTR-3B monthly.")
        assert len(calls) == 1
        assert result['pii_hits'] == []

    def test_pii_hits_are_still_reported(self):
        from guardrails.layer3_output_validator import validate_output_v2
        result = validate_output_v2("The vendor PAN is ABCDE1234F, so file the GST invoice under that PAN.")
        assert [h['type'] for h in result['pii_hits']] == ['pan_number']
