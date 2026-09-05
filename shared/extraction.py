from shared.models import PatientResponse

def classify_bmi(bmi_val: float | None):
    if bmi_val is None:
        return None
    if bmi_val < 18.5:
        return "Underweight"
    elif 18.5 <= bmi_val < 25.0:
        return "Normal"
    elif 25.0 <= bmi_val < 30.0:
        return "Overweight"
    else:
        return "Obese"

def extract_clinical_data(bundle_dict: dict):
    if not isinstance(bundle_dict, dict) or bundle_dict.get('resourceType') != 'Bundle':
        return None

    entries = bundle_dict.get("entry", [])
    if not isinstance(entries, list): 
        return None


    has_patient = any(
        entry.get('resource', {}).get('resourceType') == 'Patient'
        for entry in entries
        if isinstance(entry, dict)
    )
    if not has_patient:
        return None

    patient_info = {'raw_bundle': bundle_dict}
    latest_height_date = ""
    latest_weight_date = ""
    latest_bp_date = ""
    height_cm = None
    weight_kg = None
    latest_systolic = None
    latest_diastolic = None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get('resource')
        if not isinstance(resource, dict):
            continue

        if resource:
            if resource.get('resourceType') == 'Patient':
                patient_info['id'] = resource.get('id')
                patient_info['gender'] = resource.get('gender')
                patient_info['birth_date'] = resource.get('birthDate')

            elif resource.get('resourceType') == 'Observation':
                obs_date = resource.get('effectiveDateTime', '')
                if not obs_date:
                    continue

                codes = (resource.get('code') or {}).get('coding', [])
                for code in codes:
                    #height in cm
                    if code.get('code') == '8302-2' and obs_date >= latest_height_date: 
                        height_cm = (resource.get('valueQuantity') or {}).get('value')
                        latest_height_date = obs_date
                    #weight in kg
                    elif code.get('code') == '29463-7' and obs_date >= latest_weight_date: 
                        weight_kg = (resource.get('valueQuantity') or {}).get('value')
                        latest_weight_date = obs_date
                    #blood pressure
                    elif code.get('code') == '85354-9' and obs_date >= latest_bp_date: 
                        latest_bp_date = obs_date
                        # systolic and diastolic values
                        for component in resource.get('component', []):
                            if (component.get('code') or {}).get('coding', []):
                                for coding in (component.get('code') or {}).get('coding', []):
                                    val = (component.get('valueQuantity') or {}).get('value')
                                    if val is not None:
                                        #systolic
                                        if coding.get('code') == '8480-6': 
                                            latest_systolic = int(round(val))
                                        #diastolic
                                        elif coding.get('code') == '8462-4':
                                            latest_diastolic = int(round(val))

    patient_info['height_cm'] = height_cm
    patient_info['weight_kg'] = weight_kg
    patient_info['latest_systolic_bp'] = latest_systolic
    patient_info['latest_diastolic_bp'] = latest_diastolic

    #bmi column creation
    if height_cm is not None and weight_kg is not None:
        if height_cm > 0 and weight_kg > 0:
            bmi_calc = round(weight_kg / ((height_cm / 100) ** 2), 1)
        else:
            bmi_calc = None
        patient_info['bmi'] = bmi_calc
        patient_info['bmi_category'] = classify_bmi(bmi_calc)
    else:
        patient_info['bmi'] = None
        patient_info['bmi_category'] = None

    if 'id' in patient_info:
        return PatientResponse(**patient_info).model_dump()

    return None