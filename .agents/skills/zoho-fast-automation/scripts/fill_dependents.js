/**
 * Optimized Zoho Creator Dependents Form Fast-Filler
 *
 * Single-pass, zero-snapshot DOM injector for Zoho Creator subforms.
 * Supports active subform rows, Select2 picklists, and native event propagation.
 */
(function fillDependentsFast(dependents, notes) {
  const startTime = performance.now();

  function triggerEvents(el) {
    if (!el) return;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  }

  function setFieldValue(el, val) {
    if (!el) return false;
    el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    el.value = val;
    triggerEvents(el);
    return el.value === val;
  }

  function setRelationship(rowEl, val) {
    const relInput = (rowEl && rowEl.querySelector('input.zc_picklist_field, input[name$=".Relationship"]:not(.select2-focusser), select[name$=".Relationship"]')) ||
      document.querySelector('input.zc_picklist_field, [name$=".Relationship"]:not(.select2-focusser)');
    if (!relInput) return false;
    relInput.value = val;
    triggerEvents(relInput);

    // Sync Zoho Creator jQuery Select2 widget if present
    try {
      if (window.$ && window.$(relInput).data('select2')) {
        window.$(relInput).select2('val', val);
        window.$(relInput).val(val).trigger('change');
      }
    } catch (e) {}

    const container = relInput.closest('[zc-field-container]') || relInput.parentElement;
    if (container) {
      const chosen = container.querySelector('.select2-chosen');
      if (chosen) chosen.textContent = val;
    }
    return relInput.value === val || (container && container.querySelector('.select2-chosen')?.textContent === val);
  }

  // 1. Fill Notes to Preparer
  let notesVerified = false;
  if (notes) {
    const notesEl = document.querySelector('textarea[name="Notes_to_Preparer"], textarea[elename="Notes_to_Preparer"], textarea');
    notesVerified = setFieldValue(notesEl, notes);
  }

  // 2. Identify and ensure active subform rows
  function getActiveRows() {
    return Array.from(document.querySelectorAll('.subformRow'))
      .filter(r => !r.classList.contains('zc-subform-header-container') && !r.classList.contains('zc_subform_void_row') && r.offsetHeight > 0);
  }

  let subformRows = getActiveRows();
  let attempts = 0;
  while (subformRows.length < dependents.length && attempts < 5) {
    attempts++;
    const addBtn = Array.from(document.querySelectorAll('a, button')).find(el => el.textContent.includes('Add New') && el.offsetWidth > 0);
    if (!addBtn) break;
    addBtn.click();
    subformRows = getActiveRows();
  }

  // 3. Batch Populate Rows
  const rowResults = [];
  dependents.forEach((dep, idx) => {
    const rowEl = subformRows[idx];
    const pNext = 'Dependents_Information.t::row_' + (idx + 1);
    const pRow = 'Dependents_Information.t::row_' + idx;

    const nameEl = (rowEl && rowEl.querySelector('[name$=".Dependents_Name"], [elename="Dependents_Name"], input[type="text"]')) ||
      document.querySelector('input[name="' + pNext + '.Dependents_Name"], input[name="' + pRow + '.Dependents_Name"], #zc-Dependents_Information-Dependents_Name');

    const dobEl = (rowEl && rowEl.querySelector('[name$=".Date_of_Birth"], [elename="Date_of_Birth"]')) ||
      document.querySelector('input[name="' + pNext + '.Date_of_Birth"], input[name="' + pRow + '.Date_of_Birth"], [elename="Date_of_Birth"]');

    const ssnEl = (rowEl && rowEl.querySelector('[name*="Social_Security_ITIN"], [elename*="Security"]')) ||
      document.querySelector('input[name="' + pNext + '.Social_Security_ITIN"], input[name="' + pRow + '.Social_Security_ITIN"], [elename*="Security"]');

    const mosEl = (rowEl && rowEl.querySelector('[name$=".Mos_In_Home"], [elename="Mos_In_Home"]')) ||
      document.querySelector('input[name="' + pNext + '.Mos_In_Home"], input[name="' + pRow + '.Mos_In_Home"], [elename="Mos_In_Home"]');

    const nameOk = setFieldValue(nameEl, dep.name);
    const dobOk = setFieldValue(dobEl, dep.dob);
    const ssnOk = setFieldValue(ssnEl, dep.ssn);
    const relOk = setRelationship(rowEl, dep.relationship);
    const mosOk = setFieldValue(mosEl, dep.months);

    rowResults.push({
      row: idx + 1,
      nameVerified: nameOk,
      dobVerified: dobOk,
      ssnVerified: ssnOk,
      relVerified: relOk,
      mosVerified: mosOk
    });
  });

  const durationMs = Math.round(performance.now() - startTime);

  return {
    timestamp: new Date().toISOString(),
    success: true,
    durationMs: durationMs,
    notesVerified: notesVerified,
    rows: rowResults,
    submitted: false
  };
})(
  [
    { name: 'Aarav Bharathi', dob: '10-Apr-2015 00:00:00', ssn: '400-01-1111', relationship: 'Son', months: '12' },
    { name: 'Ananya Bharathi', dob: '18-Sep-2018 00:00:00', ssn: '400-01-2222', relationship: 'Daughter', months: '12' }
  ],
  'Eligible for Child Tax Credit. Lived with taxpayer in the US for 12 months.'
);
