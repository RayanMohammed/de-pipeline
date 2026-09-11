import uuid
from shared.models import PatientResponse, ObservationResponse, ConditionResponse

VITAL_CODES = {"8302-2": "height_cm", "29463-7": "weight_kg"}
BP_COMPONENT_LABELS = {"8480-6": "Systolic Blood Pressure", "8462-4": "Diastolic Blood Pressure"}
OBSERVATION_LABELS = {"8302-2": "Body Height", "29463-7": "Body Weight", **BP_COMPONENT_LABELS}

def classify_bmi(bmi_val: float | None):
    """
    Classifies BMI into 4 categories: Underweight, Normal, Overweight, Obese.
    Returns None if bmi_val is None.
    """
    if bmi_val is None:
        return None
    if bmi_val < 18.5:
        return "Underweight"
    elif bmi_val < 25.0:
        return "Normal"
    elif bmi_val < 30.0:
        return "Overweight"
    return "Obese"

def compute_bmi(height_cm: float | None, weight_kg: float | None):
    """
    Calculates BMI from height in centimeters and weight in kilograms.
    Returns a tuple of (bmi_value, bmi_category).
    Returns (None, None) if height_cm or weight_kg is None or non-positive.
    """
    if not height_cm or not weight_kg or height_cm <= 0 or weight_kg <= 0:
        return None, None
    bmi_calc = round(weight_kg / ((height_cm / 100) ** 2), 1)
    return bmi_calc, classify_bmi(bmi_calc)

def _extract_vital(resource, obs_id, obs_date, loinc_code):
    """
    Extracts a vital sign observation from a FHIR Observation resource.
    Returns a dictionary with observation details or None if the value is missing.
    """
    quantity = resource.get('valueQuantity') or {}
    value = quantity.get('value')
    if value is None:
        return None
    return {
        'id': obs_id, 'observation_code': loinc_code,
        'observation_description': OBSERVATION_LABELS.get(loinc_code),
        'observation_value': value, 'observation_unit': quantity.get('unit'),
        'observation_date': obs_date[:10],
    }

def _extract_bp_components(resource, obs_id, obs_date):
    """
    Extracts systolic and diastolic blood pressure components from a FHIR Observation resource.
    Returns a list of dictionaries with observation details for each component.
    """
    rows = []
    for component in resource.get('component', []):
        comp_quantity = component.get('valueQuantity') or {}
        comp_value = comp_quantity.get('value')
        if comp_value is None:
            continue
        for coding in (component.get('code') or {}).get('coding', []):
            comp_code = coding.get('code')
            if comp_code not in BP_COMPONENT_LABELS:
                continue
            rows.append({
                'id': uuid.uuid5(uuid.NAMESPACE_OID, f"{obs_id}:{comp_code}"),
                'observation_code': comp_code,
                'observation_description': BP_COMPONENT_LABELS[comp_code],
                'observation_value': comp_value, 'observation_unit': comp_quantity.get('unit'),
                'observation_date': obs_date[:10],
            })
    return rows

def _extract_condition(resource):
    """
    Extracts condition information from a FHIR Condition resource.
    Returns a dictionary with condition details or None if the resource is invalid.
    """
    onset = resource.get('onsetDateTime')
    condition_id = resource.get('id')
    if not onset or not condition_id:
        return None
    code_block = resource.get('code') or {}
    codings = code_block.get('coding', [])
    if not codings or not codings[0].get('code'):
        return None
    abatement = resource.get('abatementDateTime')
    return {
        'id': condition_id, 'condition_code': codings[0]['code'],
        'condition_description': code_block.get('text') or codings[0].get('display'),
        'start_date': onset[:10], 'end_date': abatement[:10] if abatement else None,
    }

def extract_clinical_data(bundle_dict: dict):
    """
    The heavy lifter.
    Takes a FHIR Bundle dictionary and extracts the Patient, Observations, and Conditions.
    Returns a dictionary with keys 'patient', 'observations', and 'conditions'.
    Returns None if the bundle is invalid or missing a Patient resource.
    """
    if not isinstance(bundle_dict, dict) or bundle_dict.get('resourceType') != 'Bundle':
        return None
    entries = bundle_dict.get('entry', [])
    if not isinstance(entries, list):
        return None
    has_patient = any(
        isinstance(e, dict) and e.get('resource', {}).get('resourceType') == 'Patient'
        for e in entries
    )
    if not has_patient:
        return None

    patient_info = {}
    observations_raw, conditions_raw = [], []
    latest_dates = {'8302-2': '', '29463-7': '', 'bp': ''}
    latest_values = {'height_cm': None, 'weight_kg': None, 'latest_systolic_bp': None, 'latest_diastolic_bp': None}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get('resource')
        if not isinstance(resource, dict):
            continue
        resource_type = resource.get('resourceType')

        if resource_type == 'Patient':
            patient_info['id'] = resource.get('id')
            patient_info['gender'] = resource.get('gender')
            patient_info['birth_date'] = resource.get('birthDate')
            continue

        if resource_type == 'Condition':
            condition = _extract_condition(resource)
            if condition:
                conditions_raw.append(condition)
            continue

        if resource_type != 'Observation':
            continue

        obs_id = resource.get('id')
        obs_date = resource.get('effectiveDateTime', '')
        if not obs_id or not obs_date:
            continue

        for coding in (resource.get('code') or {}).get('coding', []):
            loinc_code = coding.get('code')

            if loinc_code in VITAL_CODES:
                row = _extract_vital(resource, obs_id, obs_date, loinc_code)
                if row is None:
                    continue
                observations_raw.append(row)
                if obs_date >= latest_dates[loinc_code]:
                    latest_dates[loinc_code] = obs_date
                    latest_values[VITAL_CODES[loinc_code]] = row['observation_value']

            elif loinc_code == '85354-9':
                bp_rows = _extract_bp_components(resource, obs_id, obs_date)
                observations_raw.extend(bp_rows)
                if obs_date >= latest_dates['bp']:
                    latest_dates['bp'] = obs_date
                    for row in bp_rows:
                        rounded = int(round(row['observation_value']))
                        target = 'latest_systolic_bp' if row['observation_code'] == '8480-6' else 'latest_diastolic_bp'
                        latest_values[target] = rounded

    patient_info.update(latest_values)
    patient_info['bmi'], patient_info['bmi_category'] = compute_bmi(
        latest_values['height_cm'], latest_values['weight_kg']
    )

    if 'id' not in patient_info:
        return None
    patient_id = patient_info['id']

    observations, conditions = [], []
    for obs in observations_raw:
        obs['patient_id'] = patient_id
        observations.append(ObservationResponse(**obs).model_dump())
    for cond in conditions_raw:
        cond['patient_id'] = patient_id
        conditions.append(ConditionResponse(**cond).model_dump())

    return {'patient': PatientResponse(**patient_info).model_dump(), 'observations': observations, 'conditions': conditions}