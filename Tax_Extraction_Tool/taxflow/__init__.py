"""
taxflow — dynamic tax-packet platform:

    Upload PDF -> page analysis -> document detection -> field extraction (with page + position)
    -> Drake-style module screens -> reviewer verification / field mapping -> confirmation
    -> transfer of confirmed values into Drake Tax (Windows UI Automation).

Modules
    pdftext.py   positioned text model of a PDF (words, lines, regions) built with pdfplumber
    catalog.py   declarative catalog of tax forms: detection signatures, fields, Drake screen + module
    extract.py   layout-independent extraction engine (classify pages, split documents, read fields)
    session.py   review sessions: values, mappings, confirmations, review status (JSON on disk)
    transfer.py  Drake Tax transfer of confirmed values + Drake field discovery/linking
    routes.py    Flask blueprint: /review page and /api/review/* endpoints

Adding a new form = one entry in catalog.FORMS (detection + fields + Drake screen). Nothing in the
engine is specific to one taxpayer, one PDF or one tax year.
"""
