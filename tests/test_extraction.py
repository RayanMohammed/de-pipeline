import uuid, pytest
from shared.extraction import classify_bmi, extract_clinical_data

def test_classify_bmi_boundaries():
    assert classify_bmi(None) is None
    assert classify_bmi(18.4) == "Underweight"
    assert classify_bmi(18.5) == "Normal"
    assert classify_bmi(24.9) == "Normal"
    assert classify_bmi(25.0) == "Overweight"
    assert classify_bmi(29.9) == "Overweight"
    assert classify_bmi(30.0) == "Obese"


def test_extract_clinical_data_patient_at_end():
    p_id = str(uuid.uuid4())
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T10:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 175.0},
                }
            },
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "male",
                    "birthDate": "1992-04-15",
                }
            },
        ],
    }
    result = extract_clinical_data(bundle)
    assert result is not None
    assert str(result["id"]) == p_id
    assert result["gender"] == "male"
    assert str(result["birth_date"]) == "1992-04-15"
    assert result["height_cm"] == 175.0
    assert result["weight_kg"] is None
    assert result["bmi"] is None

def test_extract_clinical_data_updated_observation():
    p_id = str(uuid.uuid4())
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "male",
                    "birthDate": "1992-04-15",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T10:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 175.0},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-02-01T10:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 180.0},
                }
            },
        ],
    }
    result = extract_clinical_data(bundle)
    assert result is not None
    assert result["height_cm"] == 180.0  # the latest observation's value should be here

def test_extract_clinical_data_blood_pressure():
    p_id = str(uuid.uuid4())
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "female",
                    "birthDate": "1978-11-03",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-02-14T08:30:00Z",
                    "code": {"coding": [{"code": "85354-9"}]},
                    "component": [
                        {
                            "code": {"coding": [{"code": "8480-6"}]},
                            "valueQuantity": {"value": 128.4},
                        },
                        {
                            "code": {"coding": [{"code": "8462-4"}]},
                            "valueQuantity": {"value": 82.8},
                        },
                    ],
                }
            },
        ],
    }
    result = extract_clinical_data(bundle)
    assert result is not None
    assert result["latest_systolic_bp"] == 128
    assert result["latest_diastolic_bp"] == 83

def test_extract_clinical_data_bmi_calculation():
    p_id = str(uuid.uuid4())
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "male",
                    "birthDate": "2000-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T00:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 170.0},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T00:00:00Z",
                    "code": {"coding": [{"code": "29463-7"}]},
                    "valueQuantity": {"value": 72.2},
                }
            },
        ],
    }
    result = extract_clinical_data(bundle)
    assert result is not None
    assert result["bmi"] == 25.0
    assert result["bmi_category"] == "Overweight"

def test_extract_clinical_data_division_by_zero_bmi():
    p_id = str(uuid.uuid4())
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "other",
                    "birthDate": "1999-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T00:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 0.0},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "effectiveDateTime": "2024-01-01T00:00:00Z",
                    "code": {"coding": [{"code": "29463-7"}]},
                    "valueQuantity": {"value": 70.0},
                }
            },
        ],
    }
    result = extract_clinical_data(bundle)
    assert result is not None
    assert result["bmi"] is None
    assert result["bmi_category"] is None

def test_invalid_payloads_return_none():
    assert extract_clinical_data(None) is None
    assert extract_clinical_data([]) is None
    assert extract_clinical_data({}) is None
    assert extract_clinical_data({"resourceType": "Observation"}) is None
    assert extract_clinical_data({"resourceType": "Bundle", "entry": []}) is None
    assert (
        extract_clinical_data(
            {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Observation",
                            "code": {"coding": [{"code": "8302-2"}]},
                        }
                    }
                ],
            }
        )
        is None
    )