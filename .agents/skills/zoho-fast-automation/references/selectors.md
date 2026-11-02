# Zoho Creator Dependents Form Verified Selectors

Verified selectors mapped from live inspection of Zoho Creator app `drake-automation` (`creatorapp.zoho.in`).

## 1. Top-Level Form Fields
- **Notes to Preparer (Textarea)**:
  - Exact name: `textarea[name="Notes_to_Preparer"]`
  - Element attribute: `textarea[elename="Notes_to_Preparer"]`

## 2. Dependents Information Subform Grid
Zoho Creator uses dynamic row prefixes for subform entries:
`Dependents_Information.t::row_{index}.{FieldName}`

### Row 0 (First Row):
| Field | Verified Selector | Alternate Fallback |
|---|---|---|
| **Dependents Name** | `input[name="Dependents_Information.t::row_0.Dependents_Name"]` | `#zc-Dependents_Information-Dependents_Name` |
| **Date of Birth** | `input[name="Dependents_Information.t::row_0.Date_of_Birth"]` | `input[placeholder*="dd-MMM-yyyy"]` |
| **Social Security/ITIN #** | `input[name="Dependents_Information.t::row_0.Social_Security_ITIN"]` | `input[placeholder*="Social Security"]` |
| **Relationship** | `select[name="Dependents_Information.t::row_0.Relationship"]` | `.zc-Dependents_Information-Relationship select` |
| **Mos. In Home** | `input[name="Dependents_Information.t::row_0.Mos_In_Home"]` | `input[placeholder*="#######"]` |

### Row `n` (Dynamic Rows):
- **Dependents Name**: `input[name="Dependents_Information.t::row_${n}.Dependents_Name"]`
- **Date of Birth**: `input[name="Dependents_Information.t::row_${n}.Date_of_Birth"]`
- **Social Security/ITIN #**: `input[name="Dependents_Information.t::row_${n}.Social_Security_ITIN"]`
- **Relationship**: `select[name="Dependents_Information.t::row_${n}.Relationship"]`
- **Mos. In Home**: `input[name="Dependents_Information.t::row_${n}.Mos_In_Home"]`

## 3. Subform Actions
- **Add New Row Button**:
  - Selector: `a:has-text("+ Add New"), [zc-action="addrow"], [elename="add_row"], .zc-subform-addrow`
- **Submit Button (DO NOT AUTO-CLICK)**:
  - Selector: `button[elename="submit"], input[type="submit"], button:has-text("Submit")`
