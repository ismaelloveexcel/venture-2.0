from __future__ import annotations

from prospect_builder import eligible_row_to_cohort1_fields, validate_prospect


def test_validate_vp_growth_goes_review_not_reject():
    st, reason = validate_prospect(
        {
            "company_name": "Acme",
            "domain": "acme.io",
            "name": "Pat",
            "email": "pat@acme.io",
            "role": "VP Growth",
            "industry": "saas",
            "pain_signal": "x",
        }
    )
    assert st == "READY"
    assert reason == "complete_profile"


def test_validate_ambiguous_title_review():
    st, reason = validate_prospect(
        {
            "company_name": "Beta",
            "domain": "beta.io",
            "name": "Sam",
            "email": "sam@beta.io",
            "role": "Specialist II",
            "industry": "saas",
            "pain_signal": "x",
        }
    )
    assert st == "REVIEW"
    assert reason == "ambiguous_title"


def test_validate_excluded_intern_reject():
    st, reason = validate_prospect(
        {
            "company_name": "Gamma",
            "domain": "gamma.io",
            "name": "Alex",
            "email": "alex@gamma.io",
            "role": "Sales Intern",
            "industry": "saas",
            "pain_signal": "x",
        }
    )
    assert st == "REJECT"
    assert reason == "excluded_title"


def test_cohort1_bridge_prefers_first_last_and_custom_note():
    row = {
        "name": "Should Not Split",
        "first_name": "Jane",
        "last_name": "Doe",
        "company_name": "Agency Co",
        "role": "Founder",
        "email": "j@agency.co",
        "linkedin_url": "https://linkedin.com/in/j",
        "founded_year": 2023,
        "pain_signal": "scaling_outbound",
        "personalisation_note": "Custom note.",
    }
    o = eligible_row_to_cohort1_fields(row)
    assert o["first_name"] == "Jane"
    assert o["last_name"] == "Doe"
    assert o["company"] == "Agency Co"
    assert o["founded_year"] == "2023"
    assert o["estimated_clients"] == ""
    assert o["personalisation_note"] == "Custom note."


def test_cohort1_bridge_splits_name_when_no_apollo_first_last():
    row = {
        "name": "Pat Smith",
        "company_name": "X",
        "role": "Owner",
        "email": "p@x.io",
        "pain_signal": "client_acquisition",
    }
    o = eligible_row_to_cohort1_fields(row)
    assert o["first_name"] == "Pat"
    assert o["last_name"] == "Smith"
    assert "X:" in o["personalisation_note"]
