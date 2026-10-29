import os
import sys
import json
import time
from flask import Flask, request, jsonify, render_template_string, send_file
import zoho_api
from date_utils import format_to_drake_date

# Dedicated PDF modules
from extractor import extract_w2_from_pdf
from drake_w2_filler import populate_w2_screen, save_and_exit_w2, discard_w2_screen
from packet_extractor import extract_all_modules_from_packet
from drake_packet_filler import populate_all_packet_modules, populate_single_packet_module, save_and_exit_packet_screen, open_drake_screen
import packet_history_manager as history_mgr

# Dedicated Excel modules
from excel_extractor import extract_excel_organizer
from drake_excel_filler import populate_excel_return, save_and_exit_excel, discard_excel

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Default Sample Paths
default_pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Weaver-Cummings_2025_Tax_Packet.pdf"))
default_excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx"))
active_pdf_path = default_pdf_path
active_excel_path = default_excel_path

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Drake Tax Automation - Personal Information</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;0,900;1,400&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --font: 'Lato', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    }
    body, button, input, select, textarea {
      font-family: var(--font) !important;
    }
    .step-active { background-color: #2563eb; color: white; }
    .step-done { background-color: #10b981; color: white; }
    .step-idle { background-color: #e5e7eb; color: #4b5563; }
  </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800">

  <!-- Header -->
  <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
    <div class="max-w-[1600px] mx-auto px-6 py-3.5 flex flex-col md:flex-row items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white text-xl font-bold shadow-md">
          <i class="fa-solid fa-file-invoice-dollar"></i>
        </div>
        <div>
          <h1 class="text-lg font-bold text-slate-900 leading-tight">TaxFlow AI - Drake Tax Automation</h1>
          <p class="text-xs text-slate-500">Master Excel Organizer & Form W-2 PDF Automation for Drake 2025</p>
        </div>
      </div>

      <!-- MASTER WORKFLOW MODE SELECTOR (Separate Modules) -->
      <div class="flex items-center bg-slate-100 p-1.5 rounded-2xl border border-slate-200 shadow-inner">
        <button id="nav-mode-excel" onclick="switchMainMode('excel')" class="flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition bg-white text-emerald-700 shadow border border-slate-200">
          <i class="fa-solid fa-file-excel text-emerald-600 text-sm"></i>
          <span>1. Personal Information (Creator / Excel)</span>
          <span class="px-2 py-0.5 rounded-full text-[10px] bg-emerald-100 text-emerald-800 font-extrabold">Screens 1 & 2</span>
        </button>
        <button id="nav-mode-pdf" onclick="switchMainMode('pdf')" class="flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition text-slate-600 hover:text-slate-900">
          <i class="fa-solid fa-file-pdf text-red-500 text-sm"></i>
          <span>2. Form W-2 PDF Entry</span>
          <span class="px-2 py-0.5 rounded-full text-[10px] bg-blue-100 text-blue-800 font-extrabold">Screen W2</span>
        </button>
      </div>

      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Drake 2025 Ready
        </span>
      </div>
    </div>
  </header>

  <!-- ========================================================================= -->
  <!-- MODULE 1: MASTER EXCEL ORGANIZER WORKFLOW (SCREENS 1 & 2)                  -->
  <!-- ========================================================================= -->
  <div id="view-excel-mode" class="block">
    
    <!-- Progress Bar Steps for Excel -->
    <div class="max-w-4xl mx-auto px-6 py-5">
      <div class="flex items-center justify-between relative">
        <div class="absolute left-0 top-1/2 -translate-y-1/2 w-full h-1 bg-slate-200 -z-0"></div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="xl-step-1" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow">1</div>
          <span class="text-xs font-semibold text-slate-700">1. Upload Excel Organizer</span>
        </div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="xl-step-2" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow">2</div>
          <span class="text-xs font-semibold text-slate-500">2. Review Demographics & Dependents</span>
        </div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="xl-step-3" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow">3</div>
          <span class="text-xs font-semibold text-slate-500">3. Drake Entry & Verification</span>
        </div>
      </div>
    </div>

    <main class="max-w-[1600px] mx-auto px-4 sm:px-6 pb-16">

      <!-- EXCEL STEP 1: UPLOAD -->
      <div id="excel-section-upload" class="max-w-3xl mx-auto bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
        <div class="text-center max-w-xl mx-auto">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center text-3xl">
            <i class="fa-solid fa-file-excel"></i>
          </div>
          <h2 class="text-2xl font-bold text-slate-900 mb-2">Upload Master Personal Tax Organizer</h2>
          <p class="text-slate-500 text-sm mb-6">Upload client tax organizer (.xlsx). The tool will extract Taxpayer Demographics, Spouse, Mailing Address, and Dependents for automatic Drake Tax setup.</p>

          <!-- Drag & Drop Box -->
          <div id="excel-drop-zone" class="border-2 border-dashed border-slate-300 hover:border-emerald-500 transition-colors rounded-xl p-8 cursor-pointer bg-slate-50/50">
            <input type="file" id="excel-file-input" accept=".xlsx,.xls" class="hidden">
            <p class="text-sm font-medium text-slate-700 mb-1">Drag and drop client Excel file here, or <span class="text-emerald-600 underline font-semibold">browse</span></p>
            <p class="text-xs text-slate-400">Supports .xlsx and .xls formats</p>
          </div>

          <div class="mt-6 flex items-center justify-center gap-4">
            <span class="text-xs text-slate-400">--- OR QUICK TEST ---</span>
          </div>

          <button onclick="loadSampleExcelOrganizer()" class="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 transition shadow-sm">
            <i class="fa-solid fa-file-excel text-emerald-600"></i> Load 2025 Personal Tax Organizer.xlsx
          </button>
        </div>
      </div>

      <!-- EXCEL LOADING SPINNER -->
      <div id="excel-section-loading" class="max-w-xl mx-auto hidden bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-emerald-600 border-t-transparent"></div>
        <h3 id="excel-loading-title" class="text-lg font-bold text-slate-800 mt-4">Extracting Personal Tax Organizer Data...</h3>
        <p id="excel-loading-subtitle" class="text-sm text-slate-500">Reading Demographics, Spouse, Address, and Dependents table from Excel.</p>
      </div>

      <!-- EXCEL STEP 2: REVIEW & MATCH -->
      <div id="excel-section-review" class="hidden space-y-4">
        
        <!-- ZOHO CREATOR INTEGRATION BANNER -->
        <div id="zoho-creator-banner" class="hidden p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-lg shadow-md">
              <i class="fa-solid fa-cloud-arrow-down"></i>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded-full text-[10px] bg-blue-600 text-white font-extrabold uppercase tracking-wide">Zoho Creator Live</span>
                <span class="text-xs font-semibold text-blue-900" id="zoho-banner-title">Report: All_Personal_Infos</span>
              </div>
              <div class="text-sm font-bold text-slate-900 mt-0.5" id="zoho-banner-record-info">Record ID: Loading...</div>
            </div>
          </div>
          <div class="flex items-center gap-2 self-end md:self-auto">
            <button onclick="refreshZohoRecord()" class="text-xs font-bold text-blue-700 bg-white border border-blue-300 hover:bg-blue-50 px-3 py-1.5 rounded-lg transition shadow-sm">
              <i class="fa-solid fa-rotate mr-1"></i> Re-fetch Record
            </button>
            <button onclick="openZohoConfigModal()" class="text-xs font-bold text-slate-600 bg-white border border-slate-300 hover:bg-slate-50 px-3 py-1.5 rounded-lg transition shadow-sm">
              <i class="fa-solid fa-key mr-1"></i> API Settings
            </button>
          </div>
        </div>
        
        <!-- Action Header -->
        <div class="bg-white rounded-xl border border-slate-200 p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-emerald-600 text-white flex items-center justify-center text-lg shadow">
              <i class="fa-solid fa-list-check"></i>
            </div>
            <div>
              <h3 class="font-bold text-slate-900 leading-tight">Personal Information - Review & Drake Entry</h3>
              <p class="text-xs text-slate-500">Verify Taxpayer, Spouse, Mailing Address, Residency, and Banking before 1-click injection into Drake Tax 2025.</p>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <button onclick="resetExcelUpload()" class="text-xs font-semibold text-slate-600 hover:text-slate-900 px-3.5 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 transition">
              <i class="fa-solid fa-rotate-left mr-1"></i> Re-upload Excel
            </button>
            <button onclick="sendApprovedExcelToDrake()" class="inline-flex items-center gap-2 px-6 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md transition transform hover:-translate-y-0.5">
              <i class="fa-solid fa-play"></i> Approve & Enter Client into Drake Tax
            </button>
          </div>
        </div>

        <!-- EXTRACTED REVIEW CARDS GRID (2-COLUMN BALANCED - PERSONAL INFO ONLY) -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          
          <!-- COLUMN 1: TAXPAYER & SPOUSE DEMOGRAPHICS -->
          <div class="space-y-5">
            
            <!-- Card 1: Primary Taxpayer Demographics & Filing Status -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-user"></i>
                  </span>
                  <span>1. Primary Taxpayer Demographics</span>
                </h4>
                <div class="flex items-center gap-2">
                  <span class="text-[11px] font-semibold text-slate-500">Filing Status:</span>
                  <select id="xl_filing_status" class="text-xs font-bold px-3 py-1.5 border border-slate-300 rounded-lg bg-slate-50 text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                    <option value="1">1 - Single</option>
                    <option value="2">2 - Married Filing Jointly</option>
                    <option value="3">3 - Married Filing Separately</option>
                    <option value="4">4 - Head of Household</option>
                    <option value="5">5 - Qualifying Surviving Spouse</option>
                  </select>
                </div>
              </div>

              <!-- Name Fields -->
              <div class="grid grid-cols-12 gap-3 text-xs">
                <div class="col-span-5">
                  <label class="block font-semibold text-slate-600 mb-1">First Name</label>
                  <input type="text" id="xl_tp_first" placeholder="First name" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
                <div class="col-span-2">
                  <label class="block font-semibold text-slate-600 mb-1">M.I.</label>
                  <input type="text" id="xl_tp_mi" placeholder="M" maxlength="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
                <div class="col-span-5">
                  <label class="block font-semibold text-slate-600 mb-1">Last Name</label>
                  <input type="text" id="xl_tp_last" placeholder="Last name" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
              </div>

              <!-- Identification & DOB -->
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Taxpayer SSN / ITIN</label>
                  <input type="text" id="xl_tp_ssn" placeholder="XXX-XX-XXXX" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Date of Birth (DOB)</label>
                  <input type="text" id="xl_tp_dob" placeholder="MM-DD-YYYY (e.g. 12-05-1998)" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
              </div>

              <!-- Professional & Contact Info -->
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Occupation</label>
                  <input type="text" id="xl_tp_occ" placeholder="Occupation" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Daytime / Main Phone</label>
                  <input type="text" id="xl_tp_phone" placeholder="Phone number" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
              </div>

              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Other / Cell Phone</label>
                  <input type="text" id="xl_tp_other_phone" placeholder="Cell phone" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Email Address</label>
                  <input type="email" id="xl_tp_email" placeholder="client@example.com" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                </div>
              </div>
            </div>

            <!-- Card 2: Spouse Demographics -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-user-group"></i>
                  </span>
                  <span>2. Spouse Demographics</span>
                </h4>
                <span class="text-[11px] font-semibold text-slate-400">Joint Return (MFJ/MFS)</span>
              </div>

              <!-- Spouse Name -->
              <div class="grid grid-cols-12 gap-3 text-xs">
                <div class="col-span-5">
                  <label class="block font-semibold text-slate-600 mb-1">Spouse First Name</label>
                  <input type="text" id="xl_sp_first" placeholder="Spouse first name" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-900 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
                <div class="col-span-2">
                  <label class="block font-semibold text-slate-600 mb-1">M.I.</label>
                  <input type="text" id="xl_sp_mi" placeholder="M" maxlength="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
                <div class="col-span-5">
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Last Name</label>
                  <input type="text" id="xl_sp_last" placeholder="Spouse last name" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-900 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
              </div>

              <!-- Spouse SSN & DOB -->
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse SSN / ITIN</label>
                  <input type="text" id="xl_sp_ssn" placeholder="XXX-XX-XXXX" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono font-bold text-slate-900 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Date of Birth</label>
                  <input type="text" id="xl_sp_dob" placeholder="MM-DD-YYYY (e.g. 08-24-1990)" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
              </div>

              <!-- Spouse Occupation & Contact -->
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Occupation</label>
                  <input type="text" id="xl_sp_occ" placeholder="Spouse occupation" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Main Phone</label>
                  <input type="text" id="xl_sp_phone" placeholder="Phone number" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
              </div>

              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Other Phone</label>
                  <input type="text" id="xl_sp_other_phone" placeholder="Cell phone" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Spouse Email Address</label>
                  <input type="email" id="xl_sp_email" placeholder="spouse@example.com" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none">
                </div>
              </div>
            </div>

          </div>

          <!-- COLUMN 2: ADDRESS, RESIDENCY, BANK & DEPENDENTS -->
          <div class="space-y-5">
            
            <!-- Card 3: Mailing Address -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-location-dot"></i>
                  </span>
                  <span>3. Mailing Address</span>
                </h4>
                <span class="text-[11px] font-mono font-bold bg-slate-100 text-slate-600 px-2 py-0.5 rounded">Drake Screen 1</span>
              </div>
              <div class="text-xs">
                <label class="block font-semibold text-slate-600 mb-1">Street Address</label>
                <input type="text" id="xl_addr_street" placeholder="Street Address" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-900 font-medium focus:ring-2 focus:ring-rose-500 focus:border-rose-500 outline-none">
              </div>
              <div class="grid grid-cols-12 gap-3 text-xs">
                <div class="col-span-6">
                  <label class="block font-semibold text-slate-600 mb-1">City</label>
                  <input type="text" id="xl_addr_city" placeholder="City" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 outline-none">
                </div>
                <div class="col-span-3">
                  <label class="block font-semibold text-slate-600 mb-1">State</label>
                  <input type="text" id="xl_addr_state" placeholder="IL" maxlength="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 uppercase focus:ring-2 focus:ring-rose-500 focus:border-rose-500 outline-none">
                </div>
                <div class="col-span-3">
                  <label class="block font-semibold text-slate-600 mb-1">ZIP Code</label>
                  <input type="text" id="xl_addr_zip" placeholder="ZIP Code" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-center text-slate-800 font-bold focus:ring-2 focus:ring-rose-500 focus:border-rose-500 outline-none">
                </div>
              </div>
            </div>

            <!-- Card 4: Residential Status & Physical Presence in U.S. -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-passport"></i>
                  </span>
                  <span>4. Residential Status & Physical Presence</span>
                </h4>
                <span class="text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">Substantial Presence</span>
              </div>
              <div class="text-xs">
                <label class="block font-semibold text-slate-600 mb-1">Residential Status</label>
                <input type="text" id="xl_residency_status" placeholder="e.g. US Citizen / Resident Alien / Non-Resident Alien" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none">
              </div>
              <div class="grid grid-cols-3 gap-3 text-xs pt-1">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Days in US (2025)</label>
                  <input type="text" id="xl_days_2025" placeholder="365" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Days in US (2024)</label>
                  <input type="text" id="xl_days_2024" placeholder="366" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Days in US (2023)</label>
                  <input type="text" id="xl_days_2023" placeholder="365" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-center font-bold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none">
                </div>
              </div>
            </div>

            <!-- Card 5: Direct Deposit / Banking Information -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-building-columns"></i>
                  </span>
                  <span>5. Direct Deposit & Bank Details</span>
                </h4>
                <span class="text-[11px] font-mono text-slate-400">Screen DD</span>
              </div>
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Bank Name</label>
                  <input type="text" id="xl_bank_name" placeholder="Bank Name" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-medium text-slate-800 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account Type</label>
                  <select id="xl_bank_type" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-800 bg-white focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none">
                    <option value="Checking">Checking</option>
                    <option value="Savings">Savings</option>
                  </select>
                </div>
              </div>
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Routing Number (9 Digits)</label>
                  <input type="text" id="xl_bank_routing" placeholder="Routing Number" maxlength="9" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono font-bold text-slate-800 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account Number</label>
                  <input type="text" id="xl_bank_account" placeholder="Account Number" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono font-bold text-slate-800 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none">
                </div>
              </div>
            </div>

            <!-- Card 6: Dependents Information (Drake Screen 2) -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <span class="w-7 h-7 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center text-xs">
                    <i class="fa-solid fa-children"></i>
                  </span>
                  <span>6. Dependents List (Drake Screen 2)</span>
                </h4>
                <span id="xl_dep_count_badge" class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-teal-50 text-teal-700 border border-teal-200">
                  0 Dependents Found
                </span>
              </div>
              <div class="overflow-x-auto border border-slate-200 rounded-xl">
                <table class="w-full text-left text-xs">
                  <thead class="bg-slate-50 text-slate-700 font-bold border-b border-slate-200">
                    <tr>
                      <th class="p-2.5">#</th>
                      <th class="p-2.5">Full Name</th>
                      <th class="p-2.5">Relationship</th>
                      <th class="p-2.5">SSN / ITIN</th>
                      <th class="p-2.5">DOB</th>
                      <th class="p-2.5">Mos</th>
                    </tr>
                  </thead>
                  <tbody id="xl_dependents_tbody" class="divide-y divide-slate-100 font-medium text-slate-800 bg-white">
                    <!-- Populated via JS -->
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Bottom Action CTA Banner -->
            <div class="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-6 text-white shadow-lg space-y-3">
              <div class="flex flex-col sm:flex-row items-center justify-between gap-4">
                <div>
                  <h4 class="font-bold text-base">Ready to Populate Drake Tax 2025?</h4>
                  <p class="text-xs text-blue-100 mt-0.5">Enters Screen 1 Demographics and Screen 2 Dependents automatically into Drake Tax desktop.</p>
                </div>
                <button onclick="sendApprovedExcelToDrake()" class="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-white hover:bg-blue-50 text-blue-700 font-bold text-sm shadow transition transform hover:-translate-y-0.5 shrink-0">
                  <i class="fa-solid fa-bolt text-blue-600"></i>
                  <span>Approve & Enter into Drake</span>
                </button>
              </div>
            </div>

          </div>

        </div>
      </div>

      <!-- EXCEL STEP 3: DRAKE AUTOMATION & VERIFICATION -->
      <div id="excel-section-result" class="hidden max-w-4xl mx-auto space-y-4">
        
        <!-- Status Card -->
        <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
          <div class="flex items-center gap-4">
            <div id="xl-result-icon" class="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl shadow">
              <i class="fa-solid fa-robot"></i>
            </div>
            <div>
              <h3 id="xl-result-title" class="text-xl font-bold text-slate-900">Running Drake Tax Automation...</h3>
              <p id="xl-result-subtitle" class="text-xs text-slate-500">Creating client return, entering Screen 1 Demographics and Screen 2 Dependents</p>
            </div>
          </div>
        </div>

        <!-- Verification Alert Box -->
        <div id="xl-verify-alert-box" class="hidden bg-gradient-to-r from-emerald-50 to-teal-50 border-2 border-emerald-400 rounded-2xl p-6 shadow-md transition-all">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-xl bg-emerald-600 text-white flex items-center justify-center text-2xl shadow shrink-0">
              <i class="fa-solid fa-shield-check animate-pulse"></i>
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between flex-wrap gap-2">
                <h4 class="text-base font-bold text-slate-900">Client Return & Dependents Populated in Drake!</h4>
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
                  <i class="fa-solid fa-clock"></i> Awaiting Verification
                </span>
              </div>
              <p class="text-xs text-slate-600 mt-1.5 leading-relaxed">
                Screen 1 (Demographics) and Screen 2 (Dependents) are now entered into Drake Tax 2025. Verify the numbers in Drake below. When satisfied, click below to save and return to the Data Entry Menu:
              </p>
              
              <div class="mt-4 flex flex-wrap items-center gap-3">
                <button onclick="executeExcelVerifyAndSave()" id="btn-xl-verify-save" class="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md transition transform hover:-translate-y-0.5">
                  <i class="fa-solid fa-floppy-disk"></i> Verify & Save (Exit to Menu in Drake)
                </button>
                <button onclick="executeExcelDiscard()" class="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-red-600 border border-slate-300 hover:border-red-300 bg-white rounded-xl transition">
                  <i class="fa-solid fa-xmark mr-1"></i> Discard Screen
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Live Reviewer Verification Values Panel (Displayed during Verification) -->
        <div id="xl-verification-values-panel" class="hidden bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b pb-3">
            <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
              <i class="fa-solid fa-list-check text-blue-600"></i> Data Entered into Drake Tax for Verification
            </h4>
            <span class="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              Screen 1 & Screen 2
            </span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <!-- Taxpayer & Spouse Box -->
            <div class="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-2">
              <div class="font-bold text-slate-800 border-b border-slate-200 pb-1 flex items-center justify-between">
                <span><i class="fa-solid fa-user text-blue-600 mr-1.5"></i> Primary Taxpayer & Spouse</span>
                <span id="xl_sum_filing_status" class="text-[11px] font-mono font-bold text-blue-700"></span>
              </div>
              <div class="grid grid-cols-2 gap-x-2 gap-y-1">
                <div><span class="text-slate-500">Taxpayer:</span> <strong id="xl_sum_tp_name" class="text-slate-900"></strong></div>
                <div><span class="text-slate-500">SSN:</span> <strong id="xl_sum_tp_ssn" class="font-mono text-slate-900"></strong></div>
                <div><span class="text-slate-500">DOB:</span> <span id="xl_sum_tp_dob" class="text-slate-800"></span></div>
                <div><span class="text-slate-500">Occupation:</span> <span id="xl_sum_tp_occ" class="text-slate-800"></span></div>
                <div><span class="text-slate-500">Phone:</span> <span id="xl_sum_tp_phone" class="text-slate-800"></span></div>
                <div><span class="text-slate-500">Email:</span> <span id="xl_sum_tp_email" class="text-slate-800"></span></div>
              </div>
              <div id="xl_sum_spouse_box" class="pt-2 border-t border-slate-200 grid grid-cols-2 gap-x-2 gap-y-1">
                <div><span class="text-slate-500">Spouse:</span> <strong id="xl_sum_sp_name" class="text-slate-900"></strong></div>
                <div><span class="text-slate-500">Spouse SSN:</span> <strong id="xl_sum_sp_ssn" class="font-mono text-slate-900"></strong></div>
                <div><span class="text-slate-500">Spouse DOB:</span> <span id="xl_sum_sp_dob" class="text-slate-800"></span></div>
                <div><span class="text-slate-500">Occupation:</span> <span id="xl_sum_sp_occ" class="text-slate-800"></span></div>
              </div>
            </div>

            <!-- Address & Bank Info Box -->
            <div class="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-2">
              <div class="font-bold text-slate-800 border-b border-slate-200 pb-1">
                <i class="fa-solid fa-location-dot text-indigo-600 mr-1.5"></i> Address & Direct Deposit
              </div>
              <div class="space-y-1">
                <div><span class="text-slate-500">Street Address:</span> <strong id="xl_sum_addr_street" class="text-slate-900"></strong></div>
                <div><span class="text-slate-500">City, State ZIP:</span> <strong id="xl_sum_addr_csz" class="text-slate-900"></strong></div>
              </div>
              <div class="pt-2 border-t border-slate-200 grid grid-cols-2 gap-x-2 gap-y-1">
                <div><span class="text-slate-500">Bank:</span> <strong id="xl_sum_bank_name" class="text-slate-800"></strong></div>
                <div><span class="text-slate-500">Account Type:</span> <strong id="xl_sum_bank_type" class="text-slate-800"></strong></div>
                <div><span class="text-slate-500">Routing #:</span> <span id="xl_sum_bank_routing" class="font-mono text-slate-800 font-bold"></span></div>
                <div><span class="text-slate-500">Account #:</span> <span id="xl_sum_bank_account" class="font-mono text-slate-800 font-bold"></span></div>
              </div>
            </div>
          </div>

          <!-- Dependents Table in Verification View -->
          <div class="space-y-1.5">
            <div class="font-bold text-xs text-slate-800 flex items-center justify-between">
              <span><i class="fa-solid fa-children text-emerald-600 mr-1.5"></i> Dependents Entered into Screen 2</span>
              <span id="xl_sum_dep_badge" class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800"></span>
            </div>
            <div class="overflow-x-auto border border-slate-200 rounded-lg">
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-100 text-slate-700 font-bold border-b border-slate-200">
                  <tr>
                    <th class="p-2">#</th>
                    <th class="p-2">Dependent Name</th>
                    <th class="p-2">Relationship</th>
                    <th class="p-2">SSN</th>
                    <th class="p-2">Date of Birth</th>
                    <th class="p-2">Months in Home</th>
                  </tr>
                </thead>
                <tbody id="xl_sum_dependents_tbody" class="divide-y divide-slate-100 font-medium text-slate-800 bg-white">
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Next Action Card (Shown after Save & Verify) -->
        <div id="xl-next-step-card" class="hidden bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-400 rounded-2xl p-6 shadow-md text-center space-y-3">
          <div class="w-12 h-12 mx-auto rounded-full bg-blue-600 text-white flex items-center justify-center text-2xl shadow">
            <i class="fa-solid fa-check-double"></i>
          </div>
          <h4 class="text-lg font-bold text-slate-900">Client Setup Complete in Drake Tax 2025!</h4>
          <p class="text-xs text-slate-600 max-w-lg mx-auto">Client return for <strong>Mani Bharathi</strong> is saved on the Data Entry Menu. Now proceed to <strong>Step 2: Form W-2 PDF Automation</strong> to enter W-2 wages and withholdings into this return.</p>
          <button onclick="switchMainMode('pdf')" class="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm shadow-md transition transform hover:-translate-y-0.5">
            <span>Proceed to Step 2: Form W-2 PDF Entry</span>
            <i class="fa-solid fa-arrow-right"></i>
          </button>
        </div>

        <!-- Terminal Log Box -->
        <div class="bg-slate-900 text-slate-100 p-4 rounded-xl font-mono text-xs max-h-72 overflow-y-auto space-y-1" id="xl-log-box">
          <div>[START] Connecting to Drake Tax Automation engine for Excel...</div>
        </div>

      </div>

    </main>
  </div>

  <!-- ========================================================================= -->
  <!-- MODULE 2: FORM W-2 PDF WORKFLOW (SCREEN W2)                                -->
  <!-- ========================================================================= -->
  <div id="view-pdf-mode" class="hidden">
    
    <!-- Progress Bar Steps for PDF -->
    <div class="max-w-4xl mx-auto px-6 py-5">
      <div class="flex items-center justify-between relative">
        <div class="absolute left-0 top-1/2 -translate-y-1/2 w-full h-1 bg-slate-200 -z-0"></div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="pdf-step-1" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow">1</div>
          <span class="text-xs font-semibold text-slate-700">1. Upload W-2 PDF</span>
        </div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="pdf-step-2" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow">2</div>
          <span class="text-xs font-semibold text-slate-500">2. Match & Review (Side-by-Side)</span>
        </div>
        <div class="flex flex-col items-center gap-1.5 relative z-10">
          <div id="pdf-step-3" class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow">3</div>
          <span class="text-xs font-semibold text-slate-500">3. Drake Entry & Verification</span>
        </div>
      </div>
    </div>

    <main class="max-w-[1600px] mx-auto px-4 sm:px-6 pb-16">

      <!-- PDF STEP 1: UPLOAD -->
      <div id="section-upload" class="max-w-4xl mx-auto space-y-6">
        <div class="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
          <div class="text-center max-w-xl mx-auto">
            <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center text-3xl">
              <i class="fa-solid fa-file-pdf"></i>
            </div>
            <h2 class="text-2xl font-bold text-slate-900 mb-2">Upload Form W-2 / Client Tax Packet</h2>
            <p class="text-slate-500 text-sm mb-6">Upload any client PDF (multi-page packet, W-2, scanned document). The tool will dynamically extract and map the fields side-by-side with the PDF.</p>

            <div id="drop-zone" class="border-2 border-dashed border-slate-300 hover:border-blue-500 transition-colors rounded-xl p-8 cursor-pointer bg-slate-50/50">
              <input type="file" id="file-input" accept=".pdf" class="hidden">
              <p class="text-sm font-medium text-slate-700 mb-1">Drag and drop client PDF here, or <span class="text-blue-600 underline font-semibold">browse</span></p>
              <p class="text-xs text-slate-400">Supports PDF format up to 50MB</p>
            </div>

            <div class="mt-6 flex items-center justify-center gap-4">
              <span class="text-xs text-slate-400">--- OR QUICK TEST ---</span>
            </div>

            <button onclick="loadSamplePacket()" class="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition shadow-sm">
              <i class="fa-solid fa-file-pdf text-red-500"></i> Load Weaver-Cummings 2025 Tax Packet.pdf
            </button>
          </div>
        </div>

        <!-- HISTORY PANEL: READY-MADE SAVED PACKETS -->
        <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <div class="flex items-center gap-2.5">
              <span class="w-8 h-8 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold shadow-sm">
                <i class="fa-solid fa-clock-rotate-left"></i>
              </span>
              <div>
                <h3 class="font-bold text-sm text-slate-900 leading-tight">Extraction History & Ready-Made Packets</h3>
                <p class="text-xs text-slate-500">Pick any previously extracted tax packet to instantly open its modules without re-uploading.</p>
              </div>
            </div>
            <button onclick="loadPacketHistory()" class="text-xs font-semibold text-slate-600 hover:text-blue-600 px-3 py-1 rounded-lg border border-slate-200 hover:bg-slate-50 transition flex items-center gap-1.5">
              <i class="fa-solid fa-rotate text-xs"></i> <span>Refresh</span>
            </button>
          </div>
          <div id="history-packet-list" class="space-y-3">
            <div class="text-center py-6 text-slate-400 text-xs">Loading history...</div>
          </div>
        </div>
      </div>

      <!-- PDF LOADING SPINNER -->
      <div id="section-loading" class="max-w-xl mx-auto hidden bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
        <h3 class="text-lg font-bold text-slate-800 mt-4">Extracting and Matching W-2 Fields...</h3>
        <p class="text-sm text-slate-500">Analyzing document structure, boxes, wages, withholdings, and employer details.</p>
      </div>

      <!-- PDF STEP 2: SIDE-BY-SIDE REVIEW -->
      <div id="section-review" class="hidden space-y-4">
        
        <!-- Top Action Bar -->
        <div class="bg-white rounded-xl border border-slate-200 p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center text-lg shadow">
              <i class="fa-solid fa-code-compare"></i>
            </div>
            <div>
              <h3 class="font-bold text-slate-900 leading-tight">Side-by-Side Review & Verification</h3>
              <p class="text-xs text-slate-500">Compare original PDF (left) directly with matched Drake Tax fields (right) before approving.</p>
            </div>
          </div>

          <!-- Ownership Selector (TS Code) -->
          <div class="flex items-center gap-3 bg-indigo-50 px-3.5 py-1.5 rounded-lg border border-indigo-200">
            <span class="text-xs font-bold text-indigo-900 flex items-center gap-1.5">
              <i class="fa-solid fa-user-tag text-indigo-600"></i> Ownership:
            </span>
            <label class="inline-flex items-center gap-1.5 cursor-pointer text-xs font-bold text-slate-800">
              <input type="radio" name="ts_code_radio" value="T" id="ts_radio_t" class="w-3.5 h-3.5 text-indigo-600" checked onchange="document.getElementById('ts_code').value='T'">
              <span>Taxpayer (T)</span>
            </label>
            <label class="inline-flex items-center gap-1.5 cursor-pointer text-xs font-bold text-slate-800">
              <input type="radio" name="ts_code_radio" value="S" id="ts_radio_s" class="w-3.5 h-3.5 text-indigo-600" onchange="document.getElementById('ts_code').value='S'">
              <span>Spouse (S)</span>
            </label>
            <input type="hidden" id="ts_code" value="T">
          </div>

          <div class="flex items-center gap-2 flex-wrap">
            <button onclick="openHistoryModal()" class="text-xs font-semibold text-slate-700 hover:text-blue-700 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 transition inline-flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-clock-rotate-left text-blue-600"></i>
              <span>History</span>
              <span id="active-packet-pill" class="px-2 py-0.5 rounded-full text-[10px] bg-blue-100 text-blue-800 font-bold truncate max-w-[120px]">Ready</span>
            </button>
            <a href="/api/pdf-preview" target="_blank" class="text-xs font-semibold text-blue-700 hover:text-blue-900 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50/50 hover:bg-blue-100 transition inline-flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-arrow-up-right-from-square"></i> Open PDF Tab
            </a>
            <button onclick="resetToUpload()" class="text-xs font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 transition">
              <i class="fa-solid fa-rotate-left mr-1"></i> Re-upload
            </button>
            <button onclick="enterCurrentSingleModule()" class="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow transition">
              <i class="fa-solid fa-file-arrow-up"></i> Enter Single Form
            </button>
            <button onclick="approveAndSendAllPacketModules()" class="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow transition">
              <i class="fa-solid fa-bolt"></i> Batch Enter All
            </button>
          </div>
        </div>

        <!-- DYNAMIC MODULE SELECTOR BAR (Multi-Form Tax Packet Navigation) -->
        <div id="packet-module-bar-container" class="hidden bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div class="flex items-center gap-2">
              <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold shadow-sm">
                <i class="fa-solid fa-layer-group"></i>
              </span>
              <div>
                <h4 class="font-bold text-xs text-slate-900 leading-tight">
                  Detected IRS Tax Modules: <span id="packet-total-badge" class="font-mono text-blue-700">0</span> forms across <span id="packet-pages-badge" class="font-mono text-blue-700">0</span> pages
                </h4>
                <p class="text-[11px] text-slate-500">Click any tax module below to jump the PDF preview and verify extracted numbers:</p>
              </div>
            </div>
            <!-- Two Options: Single Entry or Bulk Entry -->
            <div class="flex items-center gap-2.5 flex-wrap">
              <button onclick="enterCurrentSingleModule()" id="btn-enter-single-module" class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md transition transform hover:-translate-y-0.5">
                <i class="fa-solid fa-file-arrow-up text-sm"></i>
                <span id="single-btn-label">1. Enter Single Form (P1 W-2)</span>
              </button>
              <button onclick="approveAndSendAllPacketModules()" id="btn-enter-batch-modules" class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-md transition transform hover:-translate-y-0.5">
                <i class="fa-solid fa-bolt text-sm"></i>
                <span>2. Batch Enter All (17 Modules)</span>
              </button>
            </div>
          </div>
          <!-- Horizontal Scrollable Pills -->
          <div id="packet-module-pills" class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
            <!-- Rendered dynamically -->
          </div>
        </div>

        <!-- 2-COLUMN SPLIT VIEW: PDF VIEWER (LEFT) + EXTRACTED FIELDS (RIGHT) -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          <!-- LEFT: ORIGINAL PDF PREVIEW -->
          <div class="lg:col-span-6 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden sticky top-20">
            <div class="bg-slate-50 px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <div class="flex items-center gap-2 font-bold text-xs text-slate-800">
                <i class="fa-solid fa-file-pdf text-red-500 text-sm"></i>
                <span>Original Document Preview</span>
              </div>
              <span class="text-[10px] uppercase tracking-wider font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
                Form W-2 View
              </span>
            </div>
            <div class="relative bg-slate-100">
              <iframe id="pdf-preview-frame" src="/api/pdf-preview#page=1&zoom=page-width" class="w-full h-[760px] border-0" title="PDF Document Preview"></iframe>
            </div>
            <div class="bg-slate-50 px-4 py-2 text-[11px] text-slate-500 border-t border-slate-200 flex items-center justify-between">
              <span><i class="fa-solid fa-magnifying-glass-plus mr-1"></i> Interactive: zoom, scroll, or select text</span>
              <a href="/api/pdf-preview" target="_blank" class="text-blue-600 font-semibold hover:underline">Full Screen <i class="fa-solid fa-expand ml-0.5"></i></a>
            </div>
          </div>

          <!-- RIGHT: MATCHED EXTRACTED FORM FIELDS -->
          <div class="lg:col-span-6 space-y-4">
            <!-- Dynamic Non-W2 Module Card Container -->
            <div id="non-w2-module-card" class="hidden space-y-4"></div>

            <form id="w2-form" class="space-y-4">
              
              <!-- Employee Card -->
              <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h4 class="font-bold text-slate-900 border-b pb-2 mb-3 text-sm flex items-center justify-between">
                  <span class="flex items-center gap-2">
                    <i class="fa-solid fa-user text-blue-600"></i> Employee (Taxpayer) Details
                  </span>
                  <span class="text-[11px] font-mono text-slate-400">Box a / e / f</span>
                </h4>
                <div class="space-y-3 text-xs">
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Employee SSN (Box a)</label>
                    <input type="text" id="employee_ssn" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono font-bold text-sm text-slate-900">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Employee Full Name (Box e)</label>
                    <input type="text" id="employee_name" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 font-medium text-sm text-slate-900">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Street Address (Box f)</label>
                    <input type="text" id="employee_address" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm text-slate-800">
                  </div>
                  <div class="grid grid-cols-3 gap-2">
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">City</label>
                      <input type="text" id="employee_city" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">State</label>
                      <input type="text" id="employee_state" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">ZIP</label>
                      <input type="text" id="employee_zip" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                    </div>
                  </div>
                </div>
              </div>

              <!-- Employer Card -->
              <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h4 class="font-bold text-slate-900 border-b pb-2 mb-3 text-sm flex items-center justify-between">
                  <span class="flex items-center gap-2">
                    <i class="fa-solid fa-building text-blue-600"></i> Employer Details
                  </span>
                  <span class="text-[11px] font-mono text-slate-400">Box b / c</span>
                </h4>
                <div class="space-y-3 text-xs">
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Employer EIN (Box b)</label>
                    <input type="text" id="employer_ein" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono font-bold text-sm text-slate-900">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Employer Name (Box c)</label>
                    <input type="text" id="employer_name" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 font-medium text-sm text-slate-900">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Street Address</label>
                    <input type="text" id="employer_address" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                  </div>
                  <div class="grid grid-cols-3 gap-2">
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">City</label>
                      <input type="text" id="employer_city" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">State</label>
                      <input type="text" id="employer_state" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm font-bold">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">ZIP</label>
                      <input type="text" id="employer_zip" class="w-full px-2.5 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                    </div>
                  </div>
                </div>
              </div>

              <!-- Wages & Withholdings (Boxes 1-6) -->
              <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h4 class="font-bold text-slate-900 border-b pb-2 mb-3 text-sm flex items-center justify-between">
                  <span class="flex items-center gap-2">
                    <i class="fa-solid fa-coins text-amber-500"></i> Wages & Taxes (Boxes 1-6)
                  </span>
                  <span class="text-[11px] font-mono text-slate-400">IRS Form W-2</span>
                </h4>
                <div class="grid grid-cols-2 gap-3 text-xs">
                  <div class="bg-emerald-50/50 p-2.5 rounded-lg border border-emerald-200">
                    <label class="block font-bold text-emerald-900 mb-1">Box 1: Wages, tips, comp</label>
                    <input type="text" id="box1_wages" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-emerald-500 font-bold text-sm text-emerald-900 bg-white">
                  </div>
                  <div class="bg-blue-50/50 p-2.5 rounded-lg border border-blue-200">
                    <label class="block font-bold text-blue-900 mb-1">Box 2: Federal income tax</label>
                    <input type="text" id="box2_fed_withheld" class="w-full px-3 py-1.5 border rounded-lg focus:ring-2 focus:ring-blue-500 font-bold text-sm text-blue-900 bg-white">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Box 3: Social security wages</label>
                    <input type="text" id="box3_ss_wages" class="w-full px-2.5 py-1.5 border rounded-lg">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Box 4: Social security tax</label>
                    <input type="text" id="box4_ss_tax" class="w-full px-2.5 py-1.5 border rounded-lg">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Box 5: Medicare wages</label>
                    <input type="text" id="box5_medicare_wages" class="w-full px-2.5 py-1.5 border rounded-lg">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-600 mb-1">Box 6: Medicare tax withheld</label>
                    <input type="text" id="box6_medicare_tax" class="w-full px-2.5 py-1.5 border rounded-lg">
                  </div>
                </div>
              </div>

              <!-- Boxes 12, 13 & State Information -->
              <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h4 class="font-bold text-slate-900 border-b pb-2 mb-3 text-sm flex items-center justify-between">
                  <span class="flex items-center gap-2">
                    <i class="fa-solid fa-tags text-indigo-500"></i> Boxes 12, 13 & State Taxes
                  </span>
                  <span class="text-[11px] font-mono text-slate-400">Screen W-2</span>
                </h4>
                <div class="space-y-3 text-xs">
                  <div class="grid grid-cols-2 gap-3">
                    <div class="flex gap-2">
                      <div class="w-16">
                        <label class="block font-semibold text-slate-600 mb-1">Code</label>
                        <input type="text" id="box12a_code" class="w-full px-2 py-1.5 border rounded-lg font-bold text-center uppercase">
                      </div>
                      <div class="flex-1">
                        <label class="block font-semibold text-slate-600 mb-1">Box 12a Amount</label>
                        <input type="text" id="box12a_amount" class="w-full px-2.5 py-1.5 border rounded-lg">
                      </div>
                    </div>
                    <div class="flex gap-2">
                      <div class="w-16">
                        <label class="block font-semibold text-slate-600 mb-1">Code</label>
                        <input type="text" id="box12b_code" class="w-full px-2 py-1.5 border rounded-lg font-bold text-center uppercase">
                      </div>
                      <div class="flex-1">
                        <label class="block font-semibold text-slate-600 mb-1">Box 12b Amount</label>
                        <input type="text" id="box12b_amount" class="w-full px-2.5 py-1.5 border rounded-lg">
                      </div>
                    </div>
                  </div>

                  <!-- Box 13 Checkbox -->
                  <div class="p-2.5 bg-slate-50 rounded-lg border flex items-center gap-2">
                    <input type="checkbox" id="box13_retirement_plan" class="w-4 h-4 text-blue-600 rounded">
                    <label for="box13_retirement_plan" class="text-xs font-semibold text-slate-700 cursor-pointer">
                      Box 13: Retirement Plan Checkbox (Checked)
                    </label>
                  </div>

                  <!-- State Wages -->
                  <div class="grid grid-cols-3 gap-2 border-t pt-3">
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">Box 15: State</label>
                      <input type="text" id="box15_state" class="w-full px-2.5 py-1.5 border rounded-lg font-bold uppercase">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">Box 16: State Wages</label>
                      <input type="text" id="box16_state_wages" class="w-full px-2.5 py-1.5 border rounded-lg">
                    </div>
                    <div>
                      <label class="block font-semibold text-slate-600 mb-1">Box 17: State Tax</label>
                      <input type="text" id="box17_state_tax" class="w-full px-2.5 py-1.5 border rounded-lg">
                    </div>
                  </div>
                </div>
              </div>

              <!-- Submit Button -->
              <div class="pt-2">
                <button type="button" onclick="openApprovalModal()" class="w-full py-3.5 px-4 rounded-xl text-white bg-blue-600 hover:bg-blue-700 font-bold text-sm shadow-md transition transform hover:-translate-y-0.5 flex items-center justify-center gap-2">
                  <i class="fa-solid fa-circle-check"></i>
                  <span>Approve & Enter into Drake Tax 2025</span>
                </button>
              </div>

            </form>
          </div>
        </div>
      </div>

      <!-- PDF STEP 3: LIVE AUTOMATION LOGS / RESULT WITH SIDE-BY-SIDE PDF PREVIEW -->
      <div id="section-result" class="hidden space-y-4">
        
        <!-- Top Status Bar -->
        <div class="bg-white rounded-xl border border-slate-200 p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-sm">
          <div class="flex items-center gap-3">
            <div id="result-icon" class="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center text-lg shadow shrink-0">
              <i class="fa-solid fa-desktop"></i>
            </div>
            <div>
              <h3 id="result-title" class="font-bold text-slate-900 leading-tight">Form W-2 Populated in Drake Software!</h3>
              <p id="result-subtitle" class="text-xs text-slate-500">Cross-examine the PDF (left) with Drake Screen W-2 on your desktop, then click Verify & Save.</p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button onclick="showSection('review'); updateStep(2);" class="text-xs font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 transition">
              <i class="fa-solid fa-arrow-left mr-1"></i> Back to Review
            </button>
            <a href="/api/pdf-preview" target="_blank" class="text-xs font-semibold text-blue-700 hover:text-blue-900 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50/50 hover:bg-blue-100 transition inline-flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-arrow-up-right-from-square"></i> Open PDF Tab
            </a>
          </div>
        </div>

        <!-- 2-COLUMN SPLIT VIEW: PDF VIEWER (LEFT) + DRAKE VERIFY & SUMMARY (RIGHT) -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          <!-- LEFT: ORIGINAL PDF PREVIEW -->
          <div class="lg:col-span-6 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden sticky top-20">
            <div class="bg-slate-50 px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <div class="flex items-center gap-2 font-bold text-xs text-slate-800">
                <i class="fa-solid fa-file-pdf text-red-500 text-sm"></i>
                <span>Original Document (Form W-2 Preview)</span>
              </div>
              <span class="text-[10px] uppercase tracking-wider font-bold bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded-full">
                Live Preview
              </span>
            </div>
            <div class="relative bg-slate-100">
              <iframe id="pdf-result-frame" src="/api/pdf-preview#page=1&zoom=page-width" class="w-full h-[760px] border-0" title="PDF Document Preview"></iframe>
            </div>
            <div class="bg-slate-50 px-4 py-2 text-[11px] text-slate-500 border-t border-slate-200 flex items-center justify-between">
              <span><i class="fa-solid fa-magnifying-glass-plus mr-1"></i> Interactive: zoom or scroll page</span>
              <a href="/api/pdf-preview" target="_blank" class="text-blue-600 font-semibold hover:underline">Full Screen <i class="fa-solid fa-expand ml-0.5"></i></a>
            </div>
          </div>

          <!-- RIGHT: VERIFY ACTIONS, SUMMARY & TERMINAL LOGS -->
          <div class="lg:col-span-6 space-y-4">
            
            <!-- INTERACTIVE VERIFY ALERT CARD -->
            <div id="verify-alert-box" class="hidden bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-400 rounded-2xl p-5 shadow-md">
              <div class="flex items-start gap-4">
                <div class="w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center text-2xl shadow shrink-0">
                  <i class="fa-solid fa-desktop animate-pulse"></i>
                </div>
                <div class="flex-1">
                  <div class="flex items-center justify-between flex-wrap gap-2">
                    <h4 class="text-base font-bold text-slate-900">Form W-2 Injected in Drake Software!</h4>
                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
                      <i class="fa-solid fa-clock"></i> Awaiting Verification
                    </span>
                  </div>
                  <p class="text-xs text-slate-600 mt-1.5 leading-relaxed">
                    All 25 fields are currently entered on <strong>Screen W-2 in Drake Tax</strong>. Cross-examine the original PDF on the left. When satisfied, click below to save and return to the Drake menu:
                  </p>
                  
                  <div class="mt-4 flex flex-wrap items-center gap-3">
                    <button onclick="executeVerifyAndSave()" id="btn-verify-save" class="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md shadow-emerald-600/20 transition transform hover:-translate-y-0.5">
                      <i class="fa-solid fa-floppy-disk"></i> Verify & Save (Exit Screen in Drake)
                    </button>
                    <button onclick="executeDiscard()" id="btn-discard" class="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-red-600 border border-slate-300 hover:border-red-300 bg-white rounded-xl transition">
                      <i class="fa-solid fa-xmark mr-1"></i> Discard Screen
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- DYNAMIC INJECTED MODULE VERIFICATION PANEL -->
            <div id="injected-values-card" class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
              <div class="flex items-center justify-between border-b pb-2 flex-wrap gap-2">
                <div class="flex items-center gap-2">
                  <h4 class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                    <i class="fa-solid fa-list-check text-blue-600"></i>
                    <span id="injected-card-title">Values Injected into Drake Tax</span>
                  </h4>
                  <span id="injected-screen-badge" class="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-200 font-mono">
                    Screen W2
                  </span>
                </div>
                <span id="summary-ts-badge" class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-700">
                  Taxpayer (T)
                </span>
              </div>

              <!-- Dynamic Content Grid Container -->
              <div id="injected-grid-container" class="grid grid-cols-2 gap-2.5 text-xs">
                <!-- Dynamically populated for W-2, 1099-R, SSA-1099, 1099-INT, 1099-DIV, 1098, 5498, 1099-B -->
              </div>
            </div>

            <!-- MULTI-MODULE TAX PACKET VERIFICATION PANEL -->
            <div id="packet-verification-values-panel" class="hidden bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
              <div class="flex items-center justify-between border-b pb-2">
                <h4 class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                  <i class="fa-solid fa-layer-group text-blue-600"></i>
                  <span>All Tax Packet Modules Populated in Drake</span>
                </h4>
                <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200">
                  Screen W2, SSA, 1099, INT, DIV, A
                </span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs border border-slate-200 rounded-xl overflow-hidden">
                  <thead class="bg-slate-50 font-bold text-slate-700 border-b border-slate-200">
                    <tr>
                      <th class="p-2">#</th>
                      <th class="p-2">Form</th>
                      <th class="p-2">Payer / Issuer</th>
                      <th class="p-2 text-right">Primary Amount</th>
                      <th class="p-2 text-right">Tax Withheld</th>
                      <th class="p-2 text-center">Drake Screen</th>
                      <th class="p-2 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody id="packet_sum_tbody" class="divide-y divide-slate-100 font-medium text-slate-800 bg-white">
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Live Terminal Log Box -->
            <div class="bg-slate-900 text-slate-100 p-4 rounded-xl font-mono text-xs max-h-56 overflow-y-auto space-y-1" id="log-box">
              <div>[START] Connecting to Drake Tax Automation engine...</div>
            </div>

            <div class="flex items-center justify-end gap-3 flex-wrap" id="result-actions" style="display: none;">
              <button onclick="goToNextModule()" id="btn-next-module" class="px-5 py-2.5 rounded-xl bg-blue-600 text-white font-bold text-xs hover:bg-blue-700 shadow inline-flex items-center gap-2 transition transform hover:-translate-y-0.5">
                <i class="fa-solid fa-arrow-right"></i>
                <span>Review & Enter Next Module</span>
              </button>
              <button onclick="approveAndSendAllPacketModules()" class="px-5 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs hover:bg-emerald-700 shadow inline-flex items-center gap-2 transition transform hover:-translate-y-0.5">
                <i class="fa-solid fa-bolt"></i>
                <span>Batch Enter Remaining Modules</span>
              </button>
              <button onclick="resetToUpload()" class="px-4 py-2.5 rounded-xl border border-slate-300 text-slate-700 font-semibold text-xs hover:bg-slate-50 transition">
                Upload New Document
              </button>
            </div>
          </div>

        </div>
      </div>

    </main>
  </div>

  <!-- CONFIRMATION / APPROVAL MODAL (PDF) -->
  <div id="approval-modal" class="hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
      <div class="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl mx-auto">
        <i class="fa-solid fa-shield-check"></i>
      </div>
      <div class="text-center">
        <h3 class="text-lg font-bold text-slate-900">Approve Form W-2 for Drake?</h3>
        <p class="text-xs text-slate-500 mt-1">You are about to approve the extracted numbers and transmit them directly into Drake Tax Software.</p>
      </div>

      <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs space-y-2">
        <div class="flex justify-between">
          <span class="text-slate-500">Client SSN:</span>
          <span id="modal-ssn" class="font-bold text-slate-800">555-71-3842</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Taxpayer:</span>
          <span id="modal-name" class="font-bold text-slate-800">ZARA WEAVER-CUMMINGS</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Employer:</span>
          <span id="modal-employer" class="font-bold text-slate-800">GRANITE PEAK INDUSTRIES</span>
        </div>
        <div class="flex justify-between border-t pt-2">
          <span class="text-slate-500">Box 1 Wages:</span>
          <span id="modal-wages" class="font-bold text-emerald-600 text-sm">$213,250.00</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Ownership (TS):</span>
          <span id="modal-owner" class="font-bold text-indigo-600">Taxpayer (T)</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Federal Tax Withheld:</span>
          <span id="modal-withheld" class="font-bold text-slate-800">$51,180.00</span>
        </div>
      </div>

      <div class="flex gap-3 pt-2">
        <button onclick="closeApprovalModal()" class="flex-1 py-2.5 rounded-xl border border-slate-300 text-slate-700 font-semibold text-sm hover:bg-slate-50">
          Review Again
        </button>
        <button onclick="sendApprovedDataToDrake()" class="flex-1 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow">
          Yes, Enter in Drake
        </button>
      </div>
    </div>
  </div>

  <!-- PACKET HISTORY SWITCHER MODAL -->
  <div id="history-modal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
    <div class="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full p-6 space-y-4">
      <div class="flex items-center justify-between border-b pb-3">
        <div class="flex items-center gap-2.5">
          <span class="w-8 h-8 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold shadow-sm">
            <i class="fa-solid fa-clock-rotate-left"></i>
          </span>
          <div>
            <h3 class="font-bold text-sm text-slate-900">Switch Tax Packet</h3>
            <p class="text-xs text-slate-500">Pick any previously saved client packet to jump immediately to its modules.</p>
          </div>
        </div>
        <button onclick="closeHistoryModal()" class="text-slate-400 hover:text-slate-700 text-lg px-2">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
      <div id="modal-history-list" class="max-h-96 overflow-y-auto space-y-2.5 pr-1">
        <!-- Rendered dynamically -->
      </div>
      <div class="pt-2 border-t flex justify-end">
        <button onclick="closeHistoryModal()" class="px-4 py-2 rounded-xl border border-slate-300 text-slate-700 font-semibold text-xs hover:bg-slate-50">
          Close
        </button>
      </div>
    </div>
  </div>

  <script>
    let currentMainMode = 'excel';
    let currentW2Data = {};
    let currentExcelData = {};

    function switchMainMode(mode) {
      currentMainMode = mode;
      const btnExcel = document.getElementById('nav-mode-excel');
      const btnPdf = document.getElementById('nav-mode-pdf');
      const viewExcel = document.getElementById('view-excel-mode');
      const viewPdf = document.getElementById('view-pdf-mode');

      if (mode === 'excel') {
        btnExcel.className = 'flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition bg-white text-emerald-700 shadow border border-slate-200';
        btnPdf.className = 'flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition text-slate-600 hover:text-slate-900';
        viewExcel.classList.remove('hidden');
        viewPdf.classList.add('hidden');
      } else {
        btnPdf.className = 'flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition bg-white text-blue-700 shadow border border-slate-200';
        btnExcel.className = 'flex items-center gap-2 px-5 py-2 rounded-xl font-bold text-xs transition text-slate-600 hover:text-slate-900';
        viewPdf.classList.remove('hidden');
        viewExcel.classList.add('hidden');
        loadPacketHistory();
      }
    }

    // =========================================================================
    // EXCEL WORKFLOW JAVASCRIPT
    // =========================================================================
    const excelDropZone = document.getElementById('excel-drop-zone');
    const excelFileInput = document.getElementById('excel-file-input');

    excelDropZone.addEventListener('click', () => excelFileInput.click());
    excelFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) uploadExcelFile(e.target.files[0]);
    });
    excelDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      excelDropZone.classList.add('border-emerald-500', 'bg-emerald-50/30');
    });
    excelDropZone.addEventListener('dragleave', () => {
      excelDropZone.classList.remove('border-emerald-500', 'bg-emerald-50/30');
    });
    excelDropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      excelDropZone.classList.remove('border-emerald-500', 'bg-emerald-50/30');
      if (e.dataTransfer.files.length > 0) uploadExcelFile(e.dataTransfer.files[0]);
    });

    function showExcelSection(sec) {
      document.getElementById('excel-section-upload').classList.add('hidden');
      document.getElementById('excel-section-loading').classList.add('hidden');
      document.getElementById('excel-section-review').classList.add('hidden');
      document.getElementById('excel-section-result').classList.add('hidden');
      document.getElementById('excel-section-' + sec).classList.remove('hidden');
    }

    function updateExcelStep(step) {
      const s1 = document.getElementById('xl-step-1');
      const s2 = document.getElementById('xl-step-2');
      const s3 = document.getElementById('xl-step-3');
      [s1, s2, s3].forEach(s => s.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow');
      if (step >= 1) s1.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow';
      if (step >= 2) {
        s1.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
        s2.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow';
      }
      if (step >= 3) {
        s2.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
        s3.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
      }
    }

    function resetExcelUpload() {
      showExcelSection('upload');
      updateExcelStep(1);
    }

    async function loadSampleExcelOrganizer() {
      showExcelSection('loading');
      updateExcelStep(2);
      try {
        const resp = await fetch('/api/excel/load-sample');
        const data = await resp.json();
        if (data.success) {
          populateExcelReviewForm(data.data);
          showExcelSection('review');
        } else {
          alert('Error loading sample: ' + data.error);
          resetExcelUpload();
        }
      } catch (err) {
        alert('Failed to connect to Excel server: ' + err);
        resetExcelUpload();
      }
    }

    async function uploadExcelFile(file) {
      showExcelSection('loading');
      updateExcelStep(2);
      const fd = new FormData();
      fd.append('file', file);
      try {
        const resp = await fetch('/api/excel/extract', { method: 'POST', body: fd });
        const data = await resp.json();
        if (data.success) {
          populateExcelReviewForm(data.data);
          showExcelSection('review');
        } else {
          alert('Error extracting Excel file: ' + data.error);
          resetExcelUpload();
        }
      } catch (err) {
        alert('Upload failed: ' + err);
        resetExcelUpload();
      }
    }

    function populateExcelReviewForm(d) {
      currentExcelData = d;
      const tp = d.taxpayer || {};
      const sp = d.spouse || {};
      const addr = d.address || {};
      const bk = d.bank || {};
      const rq = d.residency_questions || {};

      // 1. Primary Taxpayer Demographics
      const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
      setVal('xl_tp_first', tp.first_name);
      setVal('xl_tp_mi', tp.mi);
      setVal('xl_tp_last', tp.last_name);
      setVal('xl_tp_ssn', tp.ssn);
      setVal('xl_tp_dob', tp.dob);
      setVal('xl_tp_occ', tp.occupation);
      setVal('xl_tp_phone', tp.phone);
      setVal('xl_tp_other_phone', tp.other_phone);
      setVal('xl_tp_email', tp.email);

      // 2. Spouse Demographics
      setVal('xl_sp_first', sp.first_name);
      setVal('xl_sp_mi', sp.mi);
      setVal('xl_sp_last', sp.last_name);
      setVal('xl_sp_ssn', sp.ssn);
      setVal('xl_sp_dob', sp.dob);
      setVal('xl_sp_occ', sp.occupation);
      setVal('xl_sp_phone', sp.phone);
      setVal('xl_sp_other_phone', sp.other_phone);
      setVal('xl_sp_email', sp.email);

      // Filing Status (default 1 if Single, 2 if Married)
      setVal('xl_filing_status', d.filing_status || '1');

      // 3. Mailing Address
      setVal('xl_addr_street', addr.street);
      setVal('xl_addr_city', addr.city);
      setVal('xl_addr_state', addr.state);
      setVal('xl_addr_zip', addr.zip);

      // 4. Residential Status & Physical Presence
      setVal('xl_residency_status', rq.residential_status);
      setVal('xl_days_2025', rq.days_2025);
      setVal('xl_days_2024', rq.days_2024);
      setVal('xl_days_2023', rq.days_2023);

      // 5. Direct Deposit / Banking
      setVal('xl_bank_name', bk.bank_name);
      const bankTypeEl = document.getElementById('xl_bank_type');
      if (bankTypeEl) {
        const bt = (bk.account_type || '').toLowerCase();
        bankTypeEl.value = bt.includes('sav') ? 'Savings' : 'Checking';
      }
      setVal('xl_bank_routing', bk.routing);
      setVal('xl_bank_account', bk.account_number);

      // 6. Dependents List
      const tbody = document.getElementById('xl_dependents_tbody');
      if (tbody) {
        tbody.innerHTML = '';
        const deps = d.dependents || [];
        const badge = document.getElementById('xl_dep_count_badge');
        if (badge) badge.textContent = deps.length + (deps.length === 1 ? ' Dependent Found' : ' Dependents Found');

        if (deps.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="p-3 text-center text-slate-400">No dependents found in this record.</td></tr>';
        } else {
          deps.forEach((dep, idx) => {
            const tr = document.createElement('tr');
            tr.className = idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50';
            tr.innerHTML = `
              <td class="p-2.5 font-bold text-slate-400">${idx + 1}</td>
              <td class="p-2.5 font-bold text-slate-900">${dep.first_name || ''} ${dep.last_name || ''}</td>
              <td class="p-2.5"><span class="px-2 py-0.5 rounded bg-teal-50 text-teal-800 font-bold">${dep.relationship || 'CHILD'}</span></td>
              <td class="p-2.5 font-mono text-slate-600">${dep.ssn || 'N/A'}</td>
              <td class="p-2.5">${dep.dob || 'N/A'}</td>
              <td class="p-2.5 font-bold">${dep.months || '12'} mos</td>
            `;
            tbody.appendChild(tr);
          });
        }
      }
    }

    async function sendApprovedExcelToDrake() {
      showExcelSection('result');
      updateExcelStep(3);

      document.getElementById('xl-verify-alert-box').classList.add('hidden');
      document.getElementById('xl-next-step-card').classList.add('hidden');

      // Package updated values
      const payload = {
        taxpayer: {
          first_name: document.getElementById('xl_tp_first').value,
          mi: document.getElementById('xl_tp_mi').value,
          last_name: document.getElementById('xl_tp_last').value,
          ssn: document.getElementById('xl_tp_ssn').value,
          dob: (document.getElementById('xl_tp_dob').value || '').trim().replace(/\//g, '-'),
          occupation: document.getElementById('xl_tp_occ').value,
          phone: document.getElementById('xl_tp_phone').value,
          other_phone: document.getElementById('xl_tp_other_phone') ? document.getElementById('xl_tp_other_phone').value : '',
          email: document.getElementById('xl_tp_email').value,
        },
        spouse: {
          first_name: document.getElementById('xl_sp_first').value,
          mi: document.getElementById('xl_sp_mi').value,
          last_name: document.getElementById('xl_sp_last').value,
          ssn: document.getElementById('xl_sp_ssn').value,
          dob: (document.getElementById('xl_sp_dob').value || '').trim().replace(/\//g, '-'),
          occupation: document.getElementById('xl_sp_occ').value,
          phone: document.getElementById('xl_sp_phone').value,
          other_phone: document.getElementById('xl_sp_other_phone') ? document.getElementById('xl_sp_other_phone').value : '',
          email: document.getElementById('xl_sp_email') ? document.getElementById('xl_sp_email').value : '',
        },
        filing_status: document.getElementById('xl_filing_status').value,
        address: {
          street: document.getElementById('xl_addr_street').value,
          city: document.getElementById('xl_addr_city').value,
          state: document.getElementById('xl_addr_state').value,
          zip: document.getElementById('xl_addr_zip').value,
        },
        residency_questions: {
          residential_status: document.getElementById('xl_residency_status') ? document.getElementById('xl_residency_status').value : '',
          days_2025: document.getElementById('xl_days_2025') ? document.getElementById('xl_days_2025').value : '',
          days_2024: document.getElementById('xl_days_2024') ? document.getElementById('xl_days_2024').value : '',
          days_2023: document.getElementById('xl_days_2023') ? document.getElementById('xl_days_2023').value : '',
        },
        bank: {
          bank_name: document.getElementById('xl_bank_name').value,
          account_type: document.getElementById('xl_bank_type').value,
          routing: document.getElementById('xl_bank_routing').value,
          account_number: document.getElementById('xl_bank_account').value,
        },
        dependents: (currentExcelData.dependents || []).map(d => ({...d, dob: (d.dob || '').replace(/\//g, '-')}))
      };

      // Populate verification values panel
      document.getElementById('xl_sum_tp_name').textContent = `${payload.taxpayer.first_name} ${payload.taxpayer.mi || ''} ${payload.taxpayer.last_name}`.trim();
      document.getElementById('xl_sum_tp_ssn').textContent = payload.taxpayer.ssn || 'N/A';
      document.getElementById('xl_sum_tp_dob').textContent = payload.taxpayer.dob || 'N/A';
      document.getElementById('xl_sum_tp_occ').textContent = payload.taxpayer.occupation || 'N/A';
      document.getElementById('xl_sum_tp_phone').textContent = payload.taxpayer.phone || 'N/A';
      document.getElementById('xl_sum_tp_email').textContent = payload.taxpayer.email || 'N/A';

      const fsMap = {'1': 'Single', '2': 'Married Filing Jointly', '3': 'Married Filing Separately', '4': 'Head of Household'};
      document.getElementById('xl_sum_filing_status').textContent = fsMap[payload.filing_status] || `Status ${payload.filing_status}`;

      if (payload.spouse.first_name || payload.spouse.last_name) {
        document.getElementById('xl_sum_spouse_box').classList.remove('hidden');
        document.getElementById('xl_sum_sp_name').textContent = `${payload.spouse.first_name} ${payload.spouse.mi || ''} ${payload.spouse.last_name}`.trim();
        document.getElementById('xl_sum_sp_ssn').textContent = payload.spouse.ssn || 'N/A';
        document.getElementById('xl_sum_sp_dob').textContent = payload.spouse.dob || 'N/A';
        document.getElementById('xl_sum_sp_occ').textContent = payload.spouse.occupation || 'N/A';
      } else {
        document.getElementById('xl_sum_spouse_box').classList.add('hidden');
      }

      document.getElementById('xl_sum_addr_street').textContent = payload.address.street || 'N/A';
      document.getElementById('xl_sum_addr_csz').textContent = `${payload.address.city || ''}, ${payload.address.state || ''} ${payload.address.zip || ''}`.trim();

      document.getElementById('xl_sum_bank_name').textContent = payload.bank.bank_name || 'N/A';
      document.getElementById('xl_sum_bank_type').textContent = payload.bank.account_type || 'N/A';
      document.getElementById('xl_sum_bank_routing').textContent = payload.bank.routing || 'N/A';
      document.getElementById('xl_sum_bank_account').textContent = payload.bank.account_number || 'N/A';

      const sumDepTbody = document.getElementById('xl_sum_dependents_tbody');
      sumDepTbody.innerHTML = '';
      const deps = payload.dependents || [];
      document.getElementById('xl_sum_dep_badge').textContent = `${deps.length} Dependents Entered`;
      deps.forEach((dep, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-50';
        tr.innerHTML = `
          <td class="p-2 font-bold text-slate-500">${idx + 1}</td>
          <td class="p-2 font-bold text-slate-900">${dep.first_name || ''} ${dep.last_name || ''}</td>
          <td class="p-2 font-semibold text-emerald-700">${dep.relationship || 'CHILD'}</td>
          <td class="p-2 font-mono">${dep.ssn || ''}</td>
          <td class="p-2">${dep.dob || ''}</td>
          <td class="p-2 font-bold">${dep.months || '12'}</td>
        `;
        sumDepTbody.appendChild(tr);
      });
      document.getElementById('xl-verification-values-panel').classList.remove('hidden');

      const logBox = document.getElementById('xl-log-box');
      logBox.innerHTML = '<div>[START] Transmitting Master Organizer to Drake Tax 2025...</div>';

      try {
        const resp = await fetch('/api/excel/populate-drake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const text = await resp.text();
        let res;
        try { res = JSON.parse(text); }
        catch (e) { throw new Error('Server returned non-JSON: ' + text.substring(0, 150)); }

        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        if (res.success) {
          document.getElementById('xl-result-title').textContent = 'Demographics & Dependents Populated in Drake!';
          document.getElementById('xl-result-subtitle').textContent = 'Review Screen 1 & Screen 2 in Drake, then click Verify & Save below.';
          document.getElementById('xl-result-icon').className = 'w-12 h-12 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl shadow';
          document.getElementById('xl-result-icon').innerHTML = '<i class="fa-solid fa-desktop"></i>';
          document.getElementById('xl-verify-alert-box').classList.remove('hidden');
          document.getElementById('xl-verification-values-panel').classList.remove('hidden');
        } else {
          document.getElementById('xl-result-title').textContent = 'Drake Automation Notification';
          document.getElementById('xl-result-subtitle').textContent = res.error || 'Please ensure Drake 2025 is running.';
          document.getElementById('xl-result-icon').className = 'w-12 h-12 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center text-2xl';
          document.getElementById('xl-result-icon').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Connection failed: ${err}</div>`;
      }
    }

    async function executeExcelVerifyAndSave() {
      const btn = document.getElementById('btn-xl-verify-save');
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Saving in Drake...';

      const logBox = document.getElementById('xl-log-box');
      logBox.innerHTML += '<div>[ACTION] Reviewer clicked Verify & Save! Saving in Drake...</div>';

      try {
        const resp = await fetch('/api/excel/verify-and-save', { method: 'POST' });
        const text = await resp.text();
        let res;
        try { res = JSON.parse(text); }
        catch (e) { throw new Error('Non-JSON: ' + text.substring(0, 150)); }

        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        if (res.success) {
          document.getElementById('xl-verify-alert-box').classList.add('hidden');
          document.getElementById('xl-next-step-card').classList.remove('hidden');
          document.getElementById('xl-result-title').textContent = 'Successfully Verified & Saved into Drake Tax!';
          document.getElementById('xl-result-subtitle').textContent = 'Client demographics and dependents are saved in Drake.';
          document.getElementById('xl-result-icon').innerHTML = '<i class="fa-solid fa-check-double"></i>';
        } else {
          alert('Error during save: ' + (res.error || 'Check Drake Tax'));
          btn.disabled = false;
          btn.innerHTML = orig;
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Save failed: ${err}</div>`;
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    }

    async function executeExcelDiscard() {
      if (!confirm('Are you sure you want to discard screen changes without saving?')) return;
      try { await fetch('/api/excel/discard', { method: 'POST' }); } catch(e){}
      resetExcelUpload();
    }

    // =========================================================================
    // PDF WORKFLOW JAVASCRIPT (SCREEN W2)
    // =========================================================================
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) uploadFile(e.target.files[0]);
    });
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('border-blue-500', 'bg-blue-50/30');
    });
    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('border-blue-500', 'bg-blue-50/30');
    });
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('border-blue-500', 'bg-blue-50/30');
      if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
    });

    function showSection(name) {
      document.getElementById('section-upload').classList.add('hidden');
      document.getElementById('section-loading').classList.add('hidden');
      document.getElementById('section-review').classList.add('hidden');
      document.getElementById('section-result').classList.add('hidden');
      document.getElementById('section-' + name).classList.remove('hidden');
    }

    function updateStep(step) {
      const b1 = document.getElementById('pdf-step-1');
      const b2 = document.getElementById('pdf-step-2');
      const b3 = document.getElementById('pdf-step-3');
      [b1, b2, b3].forEach(b => b.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-idle shadow');
      if (step >= 1) b1.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow';
      if (step >= 2) {
        b1.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
        b2.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-active shadow';
      }
      if (step >= 3) {
        b2.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
        b3.className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs step-done shadow';
      }
    }

    function resetToUpload() {
      showSection('upload');
      updateStep(1);
      loadPacketHistory();
    }

    let currentPacketModules = [];
    let selectedModuleIndex = 0;
    let currentPacketId = null;

    function openHistoryModal() {
      const modal = document.getElementById('history-modal');
      if (modal) modal.classList.remove('hidden');
      loadPacketHistory();
    }

    function closeHistoryModal() {
      const modal = document.getElementById('history-modal');
      if (modal) modal.classList.add('hidden');
    }

    function renderCategoryPills(catCounts) {
      if (!catCounts) return '';
      const colors = {
        'W-2': 'bg-emerald-50 text-emerald-700 border-emerald-200',
        '1099-R': 'bg-indigo-50 text-indigo-700 border-indigo-200',
        'SSA-1099': 'bg-amber-50 text-amber-700 border-amber-200',
        '1099-INT': 'bg-cyan-50 text-cyan-700 border-cyan-200',
        '1099-DIV': 'bg-violet-50 text-violet-700 border-violet-200',
        '1098': 'bg-rose-50 text-rose-700 border-rose-200',
        '5498': 'bg-teal-50 text-teal-700 border-teal-200',
        '1099-B': 'bg-blue-50 text-blue-700 border-blue-200'
      };
      return Object.entries(catCounts).map(([cat, count]) => {
        const shortName = cat.split(' ')[0];
        const clr = colors[shortName] || 'bg-slate-100 text-slate-700 border-slate-200';
        return `<span class="px-2 py-0.5 rounded-md border text-[10px] font-bold ${clr}">${shortName}: ${count}</span>`;
      }).join(' ');
    }

    async function loadPacketHistory() {
      const container = document.getElementById('history-packet-list');
      const modalContainer = document.getElementById('modal-history-list');
      try {
        const resp = await fetch('/api/packet/history');
        const res = await resp.json();
        if (!res.success || !res.history || res.history.length === 0) {
          if (container) {
            container.innerHTML = `
              <div class="text-center py-6 text-slate-400 text-xs">
                <i class="fa-solid fa-box-open text-2xl mb-2 block text-slate-300"></i>
                No saved packets yet. Upload a tax packet or load the sample above.
              </div>
            `;
          }
          if (modalContainer) {
            modalContainer.innerHTML = `<div class="text-center py-4 text-slate-400 text-xs">No saved packets found.</div>`;
          }
          return;
        }

        if (container) {
          container.innerHTML = res.history.map(item => `
            <div class="border border-slate-200 hover:border-blue-300 rounded-xl p-4 bg-slate-50/50 hover:bg-white transition shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div class="space-y-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-bold text-sm text-slate-900">${item.taxpayer_name || item.filename}</span>
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 font-mono">${item.total_modules} Ready-Made Modules</span>
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-200 text-slate-700">${item.total_pages} Pages</span>
                </div>
                <div class="text-xs text-slate-500 flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-slate-600"><i class="fa-solid fa-file-pdf text-red-500 mr-1"></i>${item.filename}</span>
                  <span>•</span>
                  <span><i class="fa-regular fa-clock mr-1"></i>${item.created_at}</span>
                </div>
                <div class="flex items-center gap-1.5 flex-wrap pt-1">
                  ${renderCategoryPills(item.category_counts)}
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <button onclick="openPacketFromHistory('${item.id}')" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow transition transform hover:-translate-y-0.5">
                  <i class="fa-solid fa-bolt"></i> Open Ready-Made Modules
                </button>
                <button onclick="deletePacketHistory('${item.id}', event)" class="p-2 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition" title="Delete from history">
                  <i class="fa-solid fa-trash-can"></i>
                </button>
              </div>
            </div>
          `).join('');
        }

        if (modalContainer) {
          modalContainer.innerHTML = res.history.map(item => `
            <div onclick="openPacketFromHistory('${item.id}')" class="p-3 border border-slate-200 hover:border-blue-500 rounded-xl hover:bg-blue-50/50 cursor-pointer transition flex items-center justify-between gap-3 bg-white">
              <div class="space-y-0.5">
                <div class="font-bold text-xs text-slate-900 flex items-center gap-2">
                  <span>${item.taxpayer_name || item.filename}</span>
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800 font-mono">${item.total_modules} Modules</span>
                </div>
                <p class="text-[11px] text-slate-500">${item.filename} • ${item.created_at}</p>
                <div class="pt-0.5 flex gap-1 flex-wrap">${renderCategoryPills(item.category_counts)}</div>
              </div>
              <div class="shrink-0 flex items-center gap-2">
                <span class="text-xs font-bold text-blue-600 flex items-center gap-1">Open <i class="fa-solid fa-arrow-right"></i></span>
              </div>
            </div>
          `).join('');
        }
      } catch (err) {
        console.error('Failed to load history:', err);
      }
    }

    async function openPacketFromHistory(packetId) {
      showSection('loading');
      updateStep(2);
      try {
        const resp = await fetch(`/api/packet/history/${packetId}`);
        const res = await resp.json();
        if (res.success) {
          currentPacketId = packetId;
          const pill = document.getElementById('active-packet-pill');
          if (pill) pill.textContent = (res.filename || 'Active').substring(0, 16);
          handleExtractedPacketData(res);
          showSection('review');
          closeHistoryModal();
        } else {
          alert('Error loading saved packet: ' + res.error);
          resetToUpload();
        }
      } catch (err) {
        alert('Failed to load packet from history: ' + err);
        resetToUpload();
      }
    }

    async function deletePacketHistory(packetId, evt) {
      if (evt) evt.stopPropagation();
      if (!confirm('Are you sure you want to remove this packet from history?')) return;
      try {
        await fetch(`/api/packet/history/${packetId}`, { method: 'DELETE' });
        loadPacketHistory();
      } catch (err) {
        alert('Delete failed: ' + err);
      }
    }

    async function loadSamplePacket() {
      showSection('loading');
      updateStep(2);
      try {
        const resp = await fetch('/api/load-sample');
        const res = await resp.json();
        if (res.success) {
          handleExtractedPacketData(res);
          showSection('review');
          loadPacketHistory();
        } else {
          alert('Error: ' + res.error);
          resetToUpload();
        }
      } catch (err) {
        alert('Failed to connect to extraction server: ' + err);
        resetToUpload();
      }
    }

    async function uploadFile(file) {
      showSection('loading');
      updateStep(2);
      const formData = new FormData();
      formData.append('file', file);
      try {
        const resp = await fetch('/api/extract', { method: 'POST', body: formData });
        const res = await resp.json();
        if (res.success) {
          handleExtractedPacketData(res);
          showSection('review');
          loadPacketHistory();
        } else {
          alert('Error extracting file: ' + res.error);
          resetToUpload();
        }
      } catch (err) {
        alert('Upload failed: ' + err);
        resetToUpload();
      }
    }

    function handleExtractedPacketData(res) {
      if (res.filename) {
        const pill = document.getElementById('active-packet-pill');
        if (pill) pill.textContent = res.filename.length > 18 ? res.filename.substring(0, 16) + '...' : res.filename;
      }
      if (res.is_packet && res.modules && res.modules.length > 0) {
        currentPacketModules = res.modules;
        renderModuleBar(res);
        selectPacketModule(0);
      } else {
        const bar = document.getElementById('packet-module-bar-container');
        if (bar) bar.classList.add('hidden');
        populateReviewForm(res.data);
      }
    }

    function renderModuleBar(res) {
      const container = document.getElementById('packet-module-bar-container');
      container.classList.remove('hidden');
      document.getElementById('packet-total-badge').textContent = res.total_modules || res.modules.length;
      document.getElementById('packet-pages-badge').textContent = res.total_pages || '70';

      const pillsContainer = document.getElementById('packet-module-pills');
      pillsContainer.innerHTML = '';

      const iconMap = {
        'W-2': 'fa-solid fa-file-invoice-dollar text-emerald-600',
        'SSA-1099': 'fa-solid fa-landmark text-amber-600',
        '1099-R': 'fa-solid fa-piggy-bank text-indigo-600',
        '1099-INT': 'fa-solid fa-building-columns text-cyan-600',
        '1099-DIV': 'fa-solid fa-chart-pie text-violet-600',
        '1098': 'fa-solid fa-house text-rose-600',
        '5498': 'fa-solid fa-vault text-teal-600',
        '1099-B': 'fa-solid fa-chart-line text-blue-600'
      };

      res.modules.forEach((mod, idx) => {
        const pill = document.createElement('button');
        pill.id = `mod-pill-${idx}`;
        pill.onclick = () => selectPacketModule(idx);
        pill.className = 'px-3 py-1.5 rounded-lg border text-xs font-bold whitespace-nowrap flex items-center gap-1.5 transition shrink-0 bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100';
        
        const iconClass = iconMap[mod.type] || 'fa-solid fa-file-lines text-blue-600';
        pill.innerHTML = `<i class="${iconClass}"></i> <span>${mod.type} (P${mod.page})</span>`;
        pillsContainer.appendChild(pill);
      });
    }

    function updateCurrentModuleField(field, val) {
      if (currentPacketModules && currentPacketModules[selectedModuleIndex]) {
        currentPacketModules[selectedModuleIndex][field] = val;
      }
    }

    function selectPacketModule(idx) {
      selectedModuleIndex = idx;
      const mod = currentPacketModules[idx];
      if (!mod) return;

      const singleBtnLabel = document.getElementById('single-btn-label');
      if (singleBtnLabel) {
        singleBtnLabel.textContent = `1. Enter Single Form (P${mod.page} ${mod.type})`;
      }

      currentPacketModules.forEach((_, i) => {
        const p = document.getElementById(`mod-pill-${i}`);
        if (p) {
          if (i === idx) {
            p.className = 'px-3 py-1.5 rounded-lg border-2 text-xs font-bold whitespace-nowrap flex items-center gap-1.5 transition shrink-0 bg-blue-50 border-blue-600 text-blue-800 shadow-sm';
          } else {
            p.className = 'px-3 py-1.5 rounded-lg border text-xs font-bold whitespace-nowrap flex items-center gap-1.5 transition shrink-0 bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100';
          }
        }
      });

      const pdfFrame = document.getElementById('pdf-preview-frame');
      if (pdfFrame) {
        pdfFrame.src = `/api/pdf-preview?t=${Date.now()}#page=${mod.page}&zoom=page-width`;
      }

      const w2Form = document.getElementById('w2-form');
      const nonW2Card = document.getElementById('non-w2-module-card');

      if (mod.type === 'W-2') {
        nonW2Card.classList.add('hidden');
        w2Form.classList.remove('hidden');
        populateReviewForm(mod);
      } else {
        w2Form.classList.add('hidden');
        nonW2Card.classList.remove('hidden');
        renderNonW2ModuleCard(mod);
      }
    }

    function renderNonW2ModuleCard(mod) {
      const container = document.getElementById('non-w2-module-card');
      let fieldsHtml = '';

      if (mod.type === 'SSA-1099') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Beneficiary Information Card -->
            <div class="bg-amber-50/50 border border-amber-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-amber-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-id-card text-amber-600"></i>
                <span>Beneficiary & Recipient Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 1: Beneficiary Name</label>
                  <input type="text" value="${mod.beneficiary_name || ''}" oninput="updateCurrentModuleField('beneficiary_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900 focus:ring-2 focus:ring-amber-500">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 2: Beneficiary SSN</label>
                  <input type="text" value="${mod.beneficiary_ssn || mod.ssn || ''}" oninput="updateCurrentModuleField('beneficiary_ssn', this.value); updateCurrentModuleField('ssn', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono font-bold text-sm bg-white text-slate-900 focus:ring-2 focus:ring-amber-500">
                </div>
                <div class="sm:col-span-2">
                  <label class="block font-semibold text-slate-600 mb-1">Box 10: Beneficiary Address</label>
                  <input type="text" value="${mod.beneficiary_address || ''}" oninput="updateCurrentModuleField('beneficiary_address', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white text-slate-800 focus:ring-2 focus:ring-amber-500">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 11: Claim Number</label>
                  <input type="text" value="${mod.claim_number || ''}" oninput="updateCurrentModuleField('claim_number', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono font-bold text-sm bg-white text-slate-900 focus:ring-2 focus:ring-amber-500">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer Organization</label>
                  <input type="text" value="${mod.payer || 'Social Security Administration'}" oninput="updateCurrentModuleField('payer', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white text-slate-800 focus:ring-2 focus:ring-amber-500">
                </div>
              </div>
            </div>

            <!-- Benefit & Tax Amounts Card -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-calculator text-blue-600"></i>
                <span>Benefit Amounts & Tax Withheld</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 3: Benefits Paid in 2025</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.box3_benefits_paid || '0.00'}" oninput="updateCurrentModuleField('box3_benefits_paid', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 4: Benefits Repaid to SSA</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.box4_benefits_repaid || '0.00'}" oninput="updateCurrentModuleField('box4_benefits_repaid', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="bg-emerald-50 border border-emerald-300 rounded-xl p-3">
                  <label class="block font-bold text-emerald-900 mb-1">Box 5: Net Benefits for 2025 (Drake Screen SSA)</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-emerald-700 font-bold">$</span>
                    <input type="text" value="${mod.net_benefits || mod.box5_net_benefits || '0.00'}" oninput="updateCurrentModuleField('net_benefits', this.value); updateCurrentModuleField('box5_net_benefits', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-emerald-400 rounded-lg font-bold text-base text-emerald-800 bg-white">
                  </div>
                </div>
                <div class="bg-blue-50 border border-blue-300 rounded-xl p-3">
                  <label class="block font-bold text-blue-900 mb-1">Box 7: Tax Withheld (Drake Screen SSA)</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-blue-700 font-bold">$</span>
                    <input type="text" value="${mod.tax_withheld || mod.box7_tax_withheld || '0.00'}" oninput="updateCurrentModuleField('tax_withheld', this.value); updateCurrentModuleField('box7_tax_withheld', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-blue-400 rounded-lg font-bold text-base text-blue-800 bg-white">
                  </div>
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 6: Rate of Tax</label>
                  <input type="text" value="${mod.box6_rate_of_tax || '10%'}" oninput="updateCurrentModuleField('box6_rate_of_tax', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-medium text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 8: Tax Refunded to You</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.box8_tax_refunded || '0.00'}" oninput="updateCurrentModuleField('box8_tax_refunded', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Box 9: Net Tax Withheld</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.box9_net_tax_withheld || '0.00'}" oninput="updateCurrentModuleField('box9_net_tax_withheld', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Description of Box 3</label>
                  <input type="text" value="${mod.description_box3 || ''}" oninput="updateCurrentModuleField('description_box3', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white">
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '1099-R') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Payer & Recipient Identity -->
            <div class="bg-indigo-50/40 border border-indigo-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-indigo-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-building-user text-indigo-600"></i>
                <span>Payer & Recipient Identification</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer Name</label>
                  <input type="text" value="${mod.payer || ''}" oninput="updateCurrentModuleField('payer', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer TIN / EIN</label>
                  <input type="text" value="${mod.payer_tin || ''}" oninput="updateCurrentModuleField('payer_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Recipient Name</label>
                  <input type="text" value="${mod.recipient_name || ''}" oninput="updateCurrentModuleField('recipient_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Recipient TIN / SSN</label>
                  <input type="text" value="${mod.recipient_tin || ''}" oninput="updateCurrentModuleField('recipient_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white text-slate-900">
                </div>
                <div class="sm:col-span-2">
                  <label class="block font-semibold text-slate-600 mb-1">Recipient Address</label>
                  <input type="text" value="${mod.recipient_address || ''}" oninput="updateCurrentModuleField('recipient_address', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white text-slate-800">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account Number</label>
                  <input type="text" value="${mod.account_number || ''}" oninput="updateCurrentModuleField('account_number', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">IRA / SEP / SIMPLE Plan</label>
                  <span class="inline-flex items-center gap-2 mt-1.5 text-xs font-bold ${mod.is_ira ? 'text-indigo-700 bg-indigo-100 px-3 py-1 rounded-full' : 'text-slate-500 bg-slate-100 px-3 py-1 rounded-full'}">
                    <i class="fa-solid ${mod.is_ira ? 'fa-circle-check text-indigo-600' : 'fa-circle-minus'}"></i>
                    ${mod.is_ira ? 'YES - Checked (IRA/SEP/SIMPLE)' : 'NO (Non-IRA Distribution)'}
                  </span>
                </div>
              </div>
            </div>

            <!-- Distribution Breakdown -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-money-bill-transfer text-emerald-600"></i>
                <span>Distribution & Withholding Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-emerald-50 border border-emerald-300 rounded-xl p-3">
                  <label class="block font-bold text-emerald-900 mb-1">Box 1: Gross Distribution</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-emerald-700 font-bold">$</span>
                    <input type="text" value="${mod.gross_distribution || '0.00'}" oninput="updateCurrentModuleField('gross_distribution', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-emerald-400 rounded-lg font-bold text-base text-emerald-800 bg-white">
                  </div>
                </div>
                <div class="bg-emerald-50 border border-emerald-300 rounded-xl p-3">
                  <label class="block font-bold text-emerald-900 mb-1">Box 2a: Taxable Amount</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-emerald-700 font-bold">$</span>
                    <input type="text" value="${mod.taxable_amount || '0.00'}" oninput="updateCurrentModuleField('taxable_amount', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-emerald-400 rounded-lg font-bold text-base text-emerald-800 bg-white">
                  </div>
                </div>
                <div class="bg-blue-50 border border-blue-300 rounded-xl p-3">
                  <label class="block font-bold text-blue-900 mb-1">Box 4: Federal Tax Withheld</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-blue-700 font-bold">$</span>
                    <input type="text" value="${mod.fed_tax_withheld || '0.00'}" oninput="updateCurrentModuleField('fed_tax_withheld', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-blue-400 rounded-lg font-bold text-base text-blue-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 5: Employee Contributions / Roth</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.employee_contributions || '0.00'}" oninput="updateCurrentModuleField('employee_contributions', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-indigo-50/50 border border-indigo-200 rounded-xl sm:col-span-2">
                  <label class="block font-bold text-indigo-900 mb-1">Box 7: Distribution Code(s)</label>
                  <input type="text" value="${mod.dist_code || '7'}" oninput="updateCurrentModuleField('dist_code', this.value)" class="w-32 px-3 py-1.5 border border-indigo-300 rounded-lg font-mono font-extrabold text-base text-indigo-800 bg-white">
                  <span class="text-[11px] text-slate-500 ml-2">Code 7: Normal Distribution | Code 1: Early | Code 4: Death</span>
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '1099-INT') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Payer & Recipient Info -->
            <div class="bg-cyan-50/40 border border-cyan-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-cyan-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-building-columns text-cyan-600"></i>
                <span>Payer & Financial Institution</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer Name</label>
                  <input type="text" value="${mod.payer || ''}" oninput="updateCurrentModuleField('payer', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer TIN</label>
                  <input type="text" value="${mod.payer_tin || ''}" oninput="updateCurrentModuleField('payer_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Recipient Name</label>
                  <input type="text" value="${mod.recipient_name || ''}" oninput="updateCurrentModuleField('recipient_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account Number</label>
                  <input type="text" value="${mod.account_number || ''}" oninput="updateCurrentModuleField('account_number', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div class="sm:col-span-2">
                  <label class="block font-semibold text-slate-600 mb-1">Recipient Address</label>
                  <input type="text" value="${mod.recipient_address || ''}" oninput="updateCurrentModuleField('recipient_address', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white text-slate-800">
                </div>
              </div>
            </div>

            <!-- Interest & Taxes Breakdown -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-percent text-cyan-600"></i>
                <span>Interest Income & Withholding Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-cyan-50 border border-cyan-300 rounded-xl p-3">
                  <label class="block font-bold text-cyan-900 mb-1">Box 1: Interest Income</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-cyan-700 font-bold">$</span>
                    <input type="text" value="${mod.interest_income || '0.00'}" oninput="updateCurrentModuleField('interest_income', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-cyan-400 rounded-lg font-bold text-base text-cyan-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 2: Early Withdrawal Penalty</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.early_withdrawal_penalty || '0.00'}" oninput="updateCurrentModuleField('early_withdrawal_penalty', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 3: U.S. Savings Bonds / Treasuries</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.us_savings_bonds_interest || '0.00'}" oninput="updateCurrentModuleField('us_savings_bonds_interest', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl">
                  <label class="block font-bold text-blue-900 mb-1">Box 4: Federal Tax Withheld</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-blue-700 font-bold">$</span>
                    <input type="text" value="${mod.fed_tax_withheld || '0.00'}" oninput="updateCurrentModuleField('fed_tax_withheld', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-blue-300 rounded-lg font-bold text-sm text-blue-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 8: Tax-Exempt Interest</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.tax_exempt_interest || '0.00'}" oninput="updateCurrentModuleField('tax_exempt_interest', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Fees & Other Expenses</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.investment_expenses || '0.00'}" oninput="updateCurrentModuleField('investment_expenses', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '1099-DIV') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Broker & Recipient Information -->
            <div class="bg-violet-50/40 border border-violet-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-violet-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-chart-pie text-violet-600"></i>
                <span>Broker & Account Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Broker / Payer Name</label>
                  <input type="text" value="${mod.broker || mod.payer || ''}" oninput="updateCurrentModuleField('broker', this.value); updateCurrentModuleField('payer', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Payer TIN</label>
                  <input type="text" value="${mod.payer_tin || ''}" oninput="updateCurrentModuleField('payer_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Recipient Name</label>
                  <input type="text" value="${mod.recipient_name || ''}" oninput="updateCurrentModuleField('recipient_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Recipient TIN</label>
                  <input type="text" value="${mod.recipient_tin || ''}" oninput="updateCurrentModuleField('recipient_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
              </div>
            </div>

            <!-- Dividends & Capital Gains -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-sack-dollar text-violet-600"></i>
                <span>Dividend Breakdown & Capital Gains</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-violet-50 border border-violet-300 rounded-xl p-3">
                  <label class="block font-bold text-violet-900 mb-1">Box 1a: Total Ordinary Dividends</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-violet-700 font-bold">$</span>
                    <input type="text" value="${mod.ordinary_dividends || '0.00'}" oninput="updateCurrentModuleField('ordinary_dividends', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-violet-400 rounded-lg font-bold text-base text-violet-800 bg-white">
                  </div>
                </div>
                <div class="bg-violet-50 border border-violet-300 rounded-xl p-3">
                  <label class="block font-bold text-violet-900 mb-1">Box 1b: Qualified Dividends</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-violet-700 font-bold">$</span>
                    <input type="text" value="${mod.qualified_dividends || '0.00'}" oninput="updateCurrentModuleField('qualified_dividends', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-violet-400 rounded-lg font-bold text-base text-violet-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 2a: Total Capital Gain</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.capital_gain_dist || '0.00'}" oninput="updateCurrentModuleField('capital_gain_dist', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 5: Section 199A Dividends</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.section_199a_dividends || '0.00'}" oninput="updateCurrentModuleField('section_199a_dividends', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl">
                  <label class="block font-bold text-blue-900 mb-1">Box 4: Fed Tax Withheld</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-blue-700 font-bold">$</span>
                    <input type="text" value="${mod.fed_tax_withheld || '0.00'}" oninput="updateCurrentModuleField('fed_tax_withheld', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-blue-300 rounded-lg font-bold text-sm text-blue-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 7: Foreign Tax Paid</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.foreign_tax_paid || '0.00'}" oninput="updateCurrentModuleField('foreign_tax_paid', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '1098') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Lender & Borrower Information -->
            <div class="bg-rose-50/40 border border-rose-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-rose-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-house text-rose-600"></i>
                <span>Mortgage Lender & Borrower Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Mortgage Lender / Servicer</label>
                  <input type="text" value="${mod.lender || ''}" oninput="updateCurrentModuleField('lender', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Lender TIN</label>
                  <input type="text" value="${mod.lender_tin || ''}" oninput="updateCurrentModuleField('lender_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Borrower Name</label>
                  <input type="text" value="${mod.borrower_name || ''}" oninput="updateCurrentModuleField('borrower_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account / Loan Number</label>
                  <input type="text" value="${mod.account_number || ''}" oninput="updateCurrentModuleField('account_number', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
              </div>
            </div>

            <!-- Mortgage Interest & Escrow Breakdown -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-file-invoice text-rose-600"></i>
                <span>Mortgage Interest & Escrow Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-rose-50 border border-rose-300 rounded-xl p-3">
                  <label class="block font-bold text-rose-900 mb-1">Box 1: Mortgage Interest Paid (Schedule A)</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-rose-700 font-bold">$</span>
                    <input type="text" value="${mod.mortgage_interest || '0.00'}" oninput="updateCurrentModuleField('mortgage_interest', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-rose-400 rounded-lg font-bold text-base text-rose-800 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 2: Outstanding Principal</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.outstanding_principal || '0.00'}" oninput="updateCurrentModuleField('outstanding_principal', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 3: Origination Date</label>
                  <input type="text" value="${mod.origination_date || ''}" oninput="updateCurrentModuleField('origination_date', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 9: Number of Properties</label>
                  <input type="text" value="${mod.number_of_properties || '1'}" oninput="updateCurrentModuleField('number_of_properties', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div class="p-3 bg-emerald-50 border border-emerald-300 rounded-xl sm:col-span-2">
                  <label class="block font-bold text-emerald-900 mb-1">Box 10 / Escrow: Real Estate / Property Taxes Paid</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-emerald-700 font-bold">$</span>
                    <input type="text" value="${mod.property_taxes_escrow || '0.00'}" oninput="updateCurrentModuleField('property_taxes_escrow', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-emerald-400 rounded-lg font-bold text-base text-emerald-800 bg-white">
                  </div>
                  <span class="text-[11px] text-slate-500 mt-1 block">Injected into Drake Schedule A (Screen A) Line 5b Real Estate Taxes</span>
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '5498') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Trustee & Participant Information -->
            <div class="bg-teal-50/40 border border-teal-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-teal-900 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-vault text-teal-600"></i>
                <span>Trustee / Custodian & Participant Details</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Trustee / Custodian</label>
                  <input type="text" value="${mod.trustee || ''}" oninput="updateCurrentModuleField('trustee', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Trustee TIN</label>
                  <input type="text" value="${mod.trustee_tin || ''}" oninput="updateCurrentModuleField('trustee_tin', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Participant Name</label>
                  <input type="text" value="${mod.participant_name || ''}" oninput="updateCurrentModuleField('participant_name', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Account Number & Type</label>
                  <input type="text" value="${(mod.account_number || '') + ' (' + (mod.account_type || 'IRA') + ')'}" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-slate-50" readonly>
                </div>
              </div>
            </div>

            <!-- Contributions & Valuation -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-piggy-bank text-teal-600"></i>
                <span>IRA Contributions & Year-End Valuation</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-teal-50 border border-teal-300 rounded-xl p-3">
                  <label class="block font-bold text-teal-900 mb-1">Box 3: Roth IRA Conversion Amount</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-teal-700 font-bold">$</span>
                    <input type="text" value="${mod.roth_conversion_amount || '0.00'}" oninput="updateCurrentModuleField('roth_conversion_amount', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-teal-400 rounded-lg font-bold text-base text-teal-800 bg-white">
                  </div>
                </div>
                <div class="bg-slate-50 border border-slate-200 rounded-xl p-3">
                  <label class="block font-bold text-slate-800 mb-1">Box 5: Fair Market Value (FMV)</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.fmv_of_account || '0.00'}" oninput="updateCurrentModuleField('fmv_of_account', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono font-bold text-base text-slate-900 bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 1: Traditional IRA Contributions</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.ira_contributions || '0.00'}" oninput="updateCurrentModuleField('ira_contributions', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <label class="block font-semibold text-slate-700 mb-1">Box 2: Rollover Contributions</label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-slate-400 font-bold">$</span>
                    <input type="text" value="${mod.rollover_contributions || '0.00'}" oninput="updateCurrentModuleField('rollover_contributions', this.value)" class="w-full pl-6 pr-3 py-1.5 border border-slate-300 rounded-lg font-mono text-sm bg-white">
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      } else if (mod.type === '1099-B') {
        fieldsHtml = `
          <div class="space-y-4">
            <!-- Broker Header -->
            <div class="bg-blue-50/40 border border-blue-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-blue-900 uppercase tracking-wider flex items-center justify-between">
                <span class="flex items-center gap-2">
                  <i class="fa-solid fa-chart-line text-blue-600"></i>
                  <span>Consolidated Broker 1099-B Capital Gains Summary</span>
                </span>
                <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800">
                  Form 8949 / Schedule D
                </span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Broker / Clearing Firm</label>
                  <input type="text" value="${mod.broker || ''}" oninput="updateCurrentModuleField('broker', this.value)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-bold text-sm bg-white text-slate-900">
                </div>
                <div>
                  <label class="block font-semibold text-slate-600 mb-1">Reporting Period</label>
                  <input type="text" value="Tax Year 2025 (Covered Securities)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-medium text-sm bg-slate-50" readonly>
                </div>
              </div>
            </div>

            <!-- Capital Gains Breakdown -->
            <div class="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
              <div class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <i class="fa-solid fa-arrow-trend-up text-emerald-600"></i>
                <span>Short-Term & Long-Term Realized Gain/Loss</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div class="bg-slate-50 border border-slate-200 rounded-xl p-3">
                  <span class="block text-[11px] font-bold text-slate-500 uppercase">Short-Term (Box A)</span>
                  <div class="mt-2 space-y-1">
                    <div class="flex justify-between"><span>Proceeds:</span> <span class="font-mono font-bold">$${mod.short_term_proceeds || '0.00'}</span></div>
                    <div class="flex justify-between"><span>Cost Basis:</span> <span class="font-mono">$${mod.short_term_cost_basis || '0.00'}</span></div>
                    <div class="flex justify-between border-t pt-1 font-bold text-emerald-700"><span>Net Gain:</span> <span class="font-mono">$${mod.short_term_net_gain || '0.00'}</span></div>
                  </div>
                </div>
                <div class="bg-slate-50 border border-slate-200 rounded-xl p-3">
                  <span class="block text-[11px] font-bold text-slate-500 uppercase">Long-Term (Box D)</span>
                  <div class="mt-2 space-y-1">
                    <div class="flex justify-between"><span>Proceeds:</span> <span class="font-mono font-bold">$${mod.long_term_proceeds || '0.00'}</span></div>
                    <div class="flex justify-between"><span>Cost Basis:</span> <span class="font-mono">$${mod.long_term_cost_basis || '0.00'}</span></div>
                    <div class="flex justify-between border-t pt-1 font-bold text-emerald-700"><span>Net Gain:</span> <span class="font-mono">$${mod.long_term_net_gain || '0.00'}</span></div>
                  </div>
                </div>
                <div class="bg-emerald-50 border border-emerald-300 rounded-xl p-3">
                  <span class="block text-[11px] font-bold text-emerald-900 uppercase">Grand Total (Schedule D)</span>
                  <div class="mt-2 space-y-1">
                    <div class="flex justify-between"><span>Total Proceeds:</span> <span class="font-mono font-bold text-emerald-900">$${mod.total_proceeds || '0.00'}</span></div>
                    <div class="flex justify-between"><span>Total Basis:</span> <span class="font-mono">$${mod.total_cost_basis || '0.00'}</span></div>
                    <div class="flex justify-between border-t border-emerald-300 pt-1 font-extrabold text-base text-emerald-800"><span>Grand Net Gain:</span> <span class="font-mono">$${mod.total_net_gain || '0.00'}</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      }

      container.innerHTML = `
        <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b pb-3 flex-wrap gap-2">
            <h4 class="font-bold text-slate-900 text-sm flex items-center gap-2">
              <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-extrabold shadow-sm">P${mod.page}</span>
              <span>${mod.title}</span>
            </h4>
            <div class="flex items-center gap-2">
              <span class="text-xs font-extrabold px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-sm">
                Drake Screen: ${mod.screen}
              </span>
              <button onclick="enterCurrentSingleModule()" class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow transition">
                <i class="fa-solid fa-file-arrow-up"></i> Enter Screen ${mod.screen} Only
              </button>
            </div>
          </div>
          ${fieldsHtml}
          <!-- Dedicated Single Form Action Bar at Bottom of Card -->
          <div class="pt-4 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/70 p-3.5 rounded-xl border">
            <div>
              <span class="text-xs font-bold text-slate-800 block">Single Module Mode (Screen ${mod.screen})</span>
              <span class="text-[11px] text-slate-500">Populate only this Form ${mod.type} into Drake Tax 2025 to verify side-by-side.</span>
            </div>
            <button onclick="enterCurrentSingleModule()" class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md transition transform hover:-translate-y-0.5 shrink-0">
              <i class="fa-solid fa-paper-plane"></i>
              <span>Enter ${mod.type} (P${mod.page}) into Drake</span>
            </button>
          </div>
        </div>
      `;
    }

    async function enterCurrentSingleModule() {
      if (!currentPacketModules || !currentPacketModules[selectedModuleIndex]) {
        alert('No module selected to enter.');
        return;
      }
      const mod = currentPacketModules[selectedModuleIndex];

      // If W-2 and w2-form is visible, merge any edited inputs from w2-form
      if (mod.type === 'W-2') {
        const inputs = document.getElementById('w2-form').elements;
        for (let i = 0; i < inputs.length; i++) {
          const inp = inputs[i];
          if (inp.id) {
            mod[inp.id] = inp.type === 'checkbox' ? inp.checked : inp.value;
          }
        }
      }

      showSection('result');
      updateStep(3);

      document.getElementById('verify-alert-box').classList.add('hidden');
      document.getElementById('result-actions').style.display = 'none';
      document.getElementById('result-title').textContent = `Entering ${mod.type} (P${mod.page}) into Drake Tax...`;
      document.getElementById('result-subtitle').textContent = `Injecting single record into Drake Screen ${mod.screen}. Review on your desktop when finished.`;

      // Update PDF preview to this module's page
      const pdfResFrame = document.getElementById('pdf-result-frame');
      if (pdfResFrame) {
        pdfResFrame.src = `/api/pdf-preview?t=${Date.now()}#page=${mod.page}&zoom=page-width`;
      }

      // Render dynamic values injected into Drake Tax card
      renderInjectedValues(mod);

      // Populate single module summary in the verification table
      const tbody = document.getElementById('packet_sum_tbody');
      tbody.innerHTML = '';
      let primaryAmt = mod.box1_wages || mod.net_benefits || mod.gross_distribution || mod.interest_income || mod.ordinary_dividends || mod.mortgage_interest || mod.roth_conversion_amount || mod.total_proceeds || mod.fmv_of_account || '0.00';
      let withheld = mod.box2_fed_withheld || mod.tax_withheld || mod.fed_tax_withheld || '0.00';
      let payerName = mod.payer || mod.broker || mod.lender || mod.trustee || 'Payer';
      tbody.innerHTML = `
        <tr class="hover:bg-slate-50 transition bg-blue-50/40">
          <td class="p-2 font-mono text-blue-600 font-bold text-xs">P${mod.page}</td>
          <td class="p-2"><span class="font-bold text-slate-900">${mod.type}</span></td>
          <td class="p-2 truncate max-w-[200px] text-slate-800 font-semibold">${payerName}</td>
          <td class="p-2 text-right font-bold text-slate-900 font-mono">$${primaryAmt}</td>
          <td class="p-2 text-right font-mono text-slate-600">$${withheld}</td>
          <td class="p-2 text-center"><span class="font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded text-[11px]">${mod.screen}</span></td>
          <td class="p-2 text-center" id="single-status-cell"><span class="text-blue-700 font-bold text-[11px]"><i class="fa-solid fa-spinner fa-spin mr-1"></i>Entering...</span></td>
        </tr>
      `;
      document.getElementById('packet-verification-values-panel').classList.remove('hidden');

      const logBox = document.getElementById('log-box');
      logBox.innerHTML = `<div>[SINGLE START] Preparing to enter ${mod.type} (Page ${mod.page}) into Drake Screen ${mod.screen}...</div>`;

      try {
        const resp = await fetch('/api/packet/populate-single', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ module: mod })
        });
        const res = await resp.json();
        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        const statusCell = document.getElementById('single-status-cell');
        if (res.success) {
          document.getElementById('result-title').textContent = `${mod.type} (P${mod.page}) Populated in Drake Screen ${mod.screen}!`;
          document.getElementById('result-subtitle').textContent = `Screen ${mod.screen} is now open in Drake Tax. Review on desktop, then click 'Verify & Save' below.`;
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-desktop"></i>';
          if (statusCell) statusCell.innerHTML = `<span class="text-emerald-700 font-bold text-[11px]"><i class="fa-solid fa-circle-check mr-1"></i>Populated</span>`;
          document.getElementById('verify-alert-box').classList.remove('hidden');
        } else {
          document.getElementById('result-title').textContent = 'Drake Single Entry Notification';
          document.getElementById('result-subtitle').textContent = res.error || 'Please ensure Drake 2025 is open with client return.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
          if (statusCell) statusCell.innerHTML = `<span class="text-red-600 font-bold text-[11px]"><i class="fa-solid fa-xmark mr-1"></i>Failed</span>`;
          document.getElementById('result-actions').style.display = 'flex';
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Single entry failed: ${err}</div>`;
        document.getElementById('result-actions').style.display = 'flex';
      }
    }

    function goToNextModule() {
      if (!currentPacketModules || currentPacketModules.length === 0) return;
      selectedModuleIndex = (selectedModuleIndex + 1) % currentPacketModules.length;
      showSection('review');
      updateStep(2);
      selectPacketModule(selectedModuleIndex);
    }

    async function approveAndSendAllPacketModules() {
      if (!currentPacketModules || currentPacketModules.length === 0) {
        alert('No packet modules found to enter.');
        return;
      }
      showSection('result');
      updateStep(3);

      document.getElementById('verify-alert-box').classList.add('hidden');
      document.getElementById('result-actions').style.display = 'none';
      document.getElementById('result-title').textContent = 'Entering All Tax Modules into Drake Tax...';
      document.getElementById('result-subtitle').textContent = `Batch injecting ${currentPacketModules.length} forms across Drake screens...`;
      const singleCard = document.getElementById('injected-values-card');
      if (singleCard) singleCard.classList.add('hidden');

      const tbody = document.getElementById('packet_sum_tbody');
      tbody.innerHTML = '';
      currentPacketModules.forEach((m, idx) => {
        let primaryAmt = m.box1_wages || m.net_benefits || m.gross_distribution || m.interest_income || m.ordinary_dividends || m.mortgage_interest || m.roth_conversion_amount || m.total_proceeds || m.fmv_of_account || '0.00';
        let withheld = m.box2_fed_withheld || m.tax_withheld || m.fed_tax_withheld || '0.00';
        let payerName = m.payer || m.broker || m.lender || m.trustee || 'Payer';
        tbody.innerHTML += `
          <tr class="hover:bg-slate-50 transition">
            <td class="p-2 font-mono text-slate-400 text-xs">${idx + 1}</td>
            <td class="p-2"><span class="font-bold text-slate-900">${m.type}</span> <span class="text-[10px] text-slate-400">(P${m.page})</span></td>
            <td class="p-2 truncate max-w-[200px] text-slate-800">${payerName}</td>
            <td class="p-2 text-right font-bold text-slate-900 font-mono">$${primaryAmt}</td>
            <td class="p-2 text-right font-mono text-slate-600">$${withheld}</td>
            <td class="p-2 text-center"><span class="font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded text-[11px]">${m.screen}</span></td>
            <td class="p-2 text-center"><span class="text-emerald-700 font-bold text-[11px]"><i class="fa-solid fa-circle-check mr-1"></i>Populated</span></td>
          </tr>
        `;
      });
      document.getElementById('packet-verification-values-panel').classList.remove('hidden');

      const logBox = document.getElementById('log-box');
      logBox.innerHTML = `<div>[BATCH START] Preparing to enter ${currentPacketModules.length} tax forms into Drake Tax 2025...</div>`;

      try {
        const resp = await fetch('/api/packet/populate-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ modules: currentPacketModules })
        });
        const res = await resp.json();
        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        if (res.success) {
          document.getElementById('result-title').textContent = `All ${currentPacketModules.length} Tax Modules Populated in Drake!`;
          document.getElementById('result-subtitle').textContent = 'Review fields in Drake Tax, then click Verify & Save below.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-desktop"></i>';
          document.getElementById('verify-alert-box').classList.remove('hidden');
        } else {
          document.getElementById('result-title').textContent = 'Drake Batch Entry Notification';
          document.getElementById('result-subtitle').textContent = res.error || 'Please ensure Drake 2025 is open.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
          document.getElementById('result-actions').style.display = 'flex';
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Batch entry failed: ${err}</div>`;
        document.getElementById('result-actions').style.display = 'flex';
      }
    }

    function populateReviewForm(d) {
      currentW2Data = d;
      for (const key in d) {
        const el = document.getElementById(key);
        if (el) {
          if (el.type === 'checkbox') {
            el.checked = Boolean(d[key]);
          } else {
            el.value = d[key] || '';
          }
        }
      }
      if (d.ts_code === 'S') {
        document.getElementById('ts_radio_s').checked = true;
        document.getElementById('ts_code').value = 'S';
      } else {
        document.getElementById('ts_radio_t').checked = true;
        document.getElementById('ts_code').value = 'T';
      }

      const pdfFrame = document.getElementById('pdf-preview-frame');
      if (pdfFrame) {
        pdfFrame.src = '/api/pdf-preview?t=' + Date.now() + '#page=1&zoom=page-width';
      }

      renderInjectedValues(d);
    }

    function renderInjectedValues(mod) {
      if (!mod) return;
      const card = document.getElementById('injected-values-card');
      const titleEl = document.getElementById('injected-card-title');
      const screenBadge = document.getElementById('injected-screen-badge');
      const grid = document.getElementById('injected-grid-container');
      const tsBadge = document.getElementById('summary-ts-badge');

      if (!card || !grid) return;
      card.classList.remove('hidden');

      const ts = (mod.ts_code === 'S' || document.getElementById('ts_code')?.value === 'S') ? 'Spouse (S)' : 'Taxpayer (T)';
      if (tsBadge) tsBadge.textContent = ts;

      const modType = mod.type || 'W-2';
      const screenName = mod.screen || 'W2';
      if (screenBadge) screenBadge.textContent = `Screen ${screenName}`;
      if (titleEl) titleEl.textContent = `Values Injected: Form ${modType} (Page ${mod.page || 1})`;

      const fmt = (v) => {
        if (!v || v === '0' || v === '0.00') return '$0.00';
        return '$' + String(v).replace('$', '').trim();
      };

      let html = '';

      if (modType === '1099-R') {
        const payer = mod.payer_name || mod.payer || 'MERIDIAN HOLDINGS CORP PENSION TRUST';
        const ein = mod.payer_ein || mod.payer_tin || mod.ein || '36-8571204';
        const recipient = mod.recipient_name || mod.employee_name || 'ZARA OSEI WEAVER-CUMMINGS';
        const rSsn = mod.recipient_tin || mod.recipient_ssn || '***-**-2042';

        html = `
          <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Payer Name & TIN</span>
            <span class="font-bold text-slate-900 block truncate">${payer}</span>
            <span class="font-mono text-slate-600 text-[11px]">${ein}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Recipient & TIN</span>
            <span class="font-bold text-slate-900 block truncate">${recipient}</span>
            <span class="font-mono text-slate-600 text-[11px]">${rSsn}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 1: Gross Distribution</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.gross_distribution)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 2a: Taxable Amount</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.taxable_amount)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 4: Fed Tax Withheld</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.fed_tax_withheld || mod.tax_withheld)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 7: Distribution Code</span>
            <span class="font-bold text-indigo-700 text-sm">${mod.distribution_code || '7'}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 2b Checkboxes</span>
            <span class="font-semibold text-slate-700 text-[11px]">Total Dist: ${mod.total_distribution ? 'Checked' : 'No'} | Not Det: ${mod.taxable_not_determined ? 'Checked' : 'No'}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 14: State Tax Withheld</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.state_tax_withheld)}</span>
          </div>
        `;
      } else if (modType === 'SSA-1099') {
        const ben = mod.beneficiary_name || 'ZARA OSEI WEAVER-CUMMINGS';
        const ssn = mod.beneficiary_ssn || '555-71-3842';
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Beneficiary Name & SSN</span>
            <span class="font-bold text-slate-900 block truncate">${ben} (${ssn})</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 5: Net Benefits (2025)</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.net_benefits)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 6: Voluntary Tax Withheld</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.tax_withheld)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 3: Benefits Paid</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.benefits_paid)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 7: Medicare Part B</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.medicare_premiums)}</span>
          </div>
        `;
      } else if (modType === '1099-INT') {
        const payer = mod.payer_name || mod.payer || 'Financial Institution';
        const tin = mod.payer_tin || '';
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Payer / Issuer</span>
            <span class="font-bold text-slate-900 block truncate">${payer} ${tin ? '(' + tin + ')' : ''}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 1: Interest Income</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.interest_income)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 4: Federal Tax Withheld</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.fed_tax_withheld)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 2: Early Withdrawal Penalty</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.early_withdrawal_penalty)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 8: Tax-Exempt Interest</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.tax_exempt_interest)}</span>
          </div>
        `;
      } else if (modType === '1099-DIV') {
        const broker = mod.broker || mod.payer_name || mod.payer || 'Brokerage Services';
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Broker / Payer</span>
            <span class="font-bold text-slate-900 block truncate">${broker}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 1a: Total Ordinary Dividends</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.ordinary_dividends || mod.total_ordinary_dividends)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 1b: Qualified Dividends</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.qualified_dividends)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 2a: Total Capital Gain</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.total_capital_gain)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 4: Fed Tax Withheld</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.fed_tax_withheld)}</span>
          </div>
        `;
      } else if (modType === '1098') {
        const lender = mod.lender_name || mod.lender || mod.payer || 'Mortgage Lender';
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Lender / Recipient</span>
            <span class="font-bold text-slate-900 block truncate">${lender}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 1: Mortgage Interest</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.mortgage_interest)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 2: Outstanding Principal</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.outstanding_principal)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 5: Mortgage Insurance Premiums</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.mortgage_insurance)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 10: Property Taxes</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.property_taxes)}</span>
          </div>
        `;
      } else if (modType === '5498') {
        const trustee = mod.trustee_name || mod.trustee || mod.payer || 'Trustee / Custodian';
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Trustee / Custodian</span>
            <span class="font-bold text-slate-900 block truncate">${trustee}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 3: Roth Conversion Amount</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.roth_conversion_amount)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 5: Fair Market Value (FMV)</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.fmv_of_account)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 1: Traditional IRA Contrib</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.traditional_ira_contributions)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 10: Roth IRA Contrib</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.roth_ira_contributions)}</span>
          </div>
        `;
      } else if (modType === '1099-B') {
        const broker = mod.broker_name || mod.broker || mod.payer || 'Brokerage Firm';
        const proceeds = parseFloat(mod.total_proceeds || 0);
        const basis = parseFloat(mod.total_cost_basis || 0);
        const gain = (proceeds - basis).toFixed(2);
        html = `
          <div class="col-span-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Broker</span>
            <span class="font-bold text-slate-900 block truncate">${broker}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Total Proceeds (1d)</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.total_proceeds)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Total Cost Basis (1e)</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.total_cost_basis)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Net Realized Capital Gain</span>
            <span class="font-bold text-emerald-700 font-mono">$${gain}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 4: Fed Tax Withheld</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.fed_tax_withheld)}</span>
          </div>
        `;
      } else {
        // Default W-2
        html = `
          <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Employer Name & EIN</span>
            <span class="font-bold text-slate-900 block truncate">${mod.employer_name || 'GRANITE PEAK INDUSTRIES INC'}</span>
            <span class="font-mono text-slate-600 text-[11px]">${mod.employer_ein || '83-2947156'}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Taxpayer & SSN</span>
            <span class="font-bold text-slate-900 block truncate">${mod.employee_name || 'ZARA WEAVER-CUMMINGS'}</span>
            <span class="font-mono text-slate-600 text-[11px]">${mod.employee_ssn || '555-71-3842'}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200">
            <span class="text-emerald-700 block text-[10px] uppercase font-bold">Box 1: Wages, Tips, Comp</span>
            <span class="font-bold text-emerald-800 text-sm font-mono">${fmt(mod.box1_wages)}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
            <span class="text-blue-700 block text-[10px] uppercase font-bold">Box 2: Federal Tax Withheld</span>
            <span class="font-bold text-blue-800 text-sm font-mono">${fmt(mod.box2_fed_withheld)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 3: SS Wages</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.box3_ss_wages)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 4: SS Tax</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.box4_ss_tax)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 5: Medicare Wages</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.box5_medicare_wages || mod.box5_med_wages)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 6: Medicare Tax</span>
            <span class="font-semibold text-slate-800 font-mono">${fmt(mod.box6_medicare_tax || mod.box6_med_tax)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 12a Code & Amount</span>
            <span class="font-semibold text-slate-800">${mod.box12a_code || 'None'} : ${fmt(mod.box12a_amount)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 12b Code & Amount</span>
            <span class="font-semibold text-slate-800">${mod.box12b_code || 'None'} : ${fmt(mod.box12b_amount)}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 13: Retirement Plan</span>
            <span class="font-semibold text-slate-800">${mod.box13_retirement_plan ? 'Checked' : 'Not Checked'}</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-50 border border-slate-200">
            <span class="text-slate-400 block text-[10px] font-semibold">Box 15 / 16: State & Wages</span>
            <span class="font-semibold text-slate-800">${mod.box15_state || 'WY'} : ${fmt(mod.box16_state_wages || mod.box1_wages)}</span>
          </div>
        `;
      }

      grid.innerHTML = html;

      const resultPdfFrame = document.getElementById('pdf-result-frame');
      if (resultPdfFrame) {
        resultPdfFrame.src = `/api/pdf-preview?t=${Date.now()}#page=${mod.page || 1}&zoom=page-width`;
      }
    }

    function openApprovalModal() {
      document.getElementById('modal-ssn').textContent = document.getElementById('employee_ssn').value || 'N/A';
      document.getElementById('modal-name').textContent = document.getElementById('employee_name').value || 'N/A';
      document.getElementById('modal-employer').textContent = document.getElementById('employer_name').value || 'N/A';
      document.getElementById('modal-wages').textContent = '$' + (document.getElementById('box1_wages').value || '0.00');
      document.getElementById('modal-withheld').textContent = '$' + (document.getElementById('box2_fed_withheld').value || '0.00');
      const tsVal = document.getElementById('ts_code').value;
      const tsLabel = tsVal === 'S' ? 'Spouse (S)' : 'Primary Taxpayer (T)';
      document.getElementById('modal-owner').textContent = tsLabel;
      document.getElementById('approval-modal').classList.remove('hidden');
    }

    function closeApprovalModal() {
      document.getElementById('approval-modal').classList.add('hidden');
    }

    async function sendApprovedDataToDrake() {
      closeApprovalModal();
      showSection('result');
      updateStep(3);

      document.getElementById('verify-alert-box').classList.add('hidden');
      document.getElementById('result-actions').style.display = 'none';

      const approvedData = { ...currentW2Data };
      const inputs = document.getElementById('w2-form').elements;
      for (let i = 0; i < inputs.length; i++) {
        const inp = inputs[i];
        if (inp.id) {
          approvedData[inp.id] = inp.type === 'checkbox' ? inp.checked : inp.value;
        }
      }

      renderInjectedValues(approvedData);

      const logBox = document.getElementById('log-box');
      logBox.innerHTML = '<div>[START] Transmitting approved W-2 to Drake Tax 2025...</div>';

      try {
        const resp = await fetch('/api/populate-drake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(approvedData)
        });
        const text = await resp.text();
        let res;
        try { res = JSON.parse(text); }
        catch (e) { throw new Error('Non-JSON: ' + text.substring(0, 150)); }

        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        if (res.success) {
          document.getElementById('result-title').textContent = 'Form W-2 Populated in Drake Software!';
          document.getElementById('result-subtitle').textContent = 'Review fields in Drake, then click Verify & Save below.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-desktop"></i>';
          document.getElementById('verify-alert-box').classList.remove('hidden');
        } else {
          document.getElementById('result-title').textContent = 'Drake Entry Notification';
          document.getElementById('result-subtitle').textContent = res.error || 'Please ensure Drake 2025 is open.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center text-2xl';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
          document.getElementById('result-actions').style.display = 'flex';
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Connection failed: ${err}</div>`;
        document.getElementById('result-actions').style.display = 'flex';
      }
    }

    async function executeVerifyAndSave() {
      const btn = document.getElementById('btn-verify-save');
      const originalHtml = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Saving & Exiting in Drake...';

      const logBox = document.getElementById('log-box');
      logBox.innerHTML += '<div>[ACTION] Reviewer clicked Verify & Save! Saving Screen W-2 in Drake...</div>';

      try {
        const resp = await fetch('/api/verify-and-save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const text = await resp.text();
        let res;
        try { res = JSON.parse(text); }
        catch (e) { throw new Error('Non-JSON: ' + text.substring(0, 150)); }

        if (res.logs && res.logs.length > 0) {
          logBox.innerHTML = res.logs.map(l => `<div>${l}</div>`).join('');
        }

        if (res.success) {
          document.getElementById('verify-alert-box').classList.add('hidden');
          document.getElementById('result-title').textContent = 'Successfully Verified & Saved into Drake Tax!';
          document.getElementById('result-subtitle').textContent = 'Screen has been saved and closed cleanly back to Drake Data Entry Menu.';
          document.getElementById('result-icon').className = 'w-12 h-12 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl shadow';
          document.getElementById('result-icon').innerHTML = '<i class="fa-solid fa-check-double"></i>';
          document.getElementById('result-actions').style.display = 'flex';
          btn.disabled = false;
          btn.innerHTML = originalHtml;
        } else {
          alert('Error during Save & Exit: ' + (res.error || 'Please check Drake Tax.'));
          btn.disabled = false;
          btn.innerHTML = originalHtml;
        }
      } catch (err) {
        logBox.innerHTML += `<div class="text-red-400">[ERROR] Save request failed: ${err}</div>`;
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }

    async function executeDiscard() {
      if (!confirm('Are you sure you want to discard this Screen W-2 without saving?')) return;
      try { await fetch('/api/discard-screen', { method: 'POST' }); } catch (e) {}
      resetToUpload();
    }

    // =========================================================================
    // ZOHO CREATOR AUTOMATION & REST API INTEGRATION
    // =========================================================================
    let currentCreatorRecordId = null;

    async function initZohoCreatorMode(recordId) {
      currentCreatorRecordId = recordId;
      switchMainMode('excel');
      showExcelSection('loading');
      updateExcelStep(2);

      const titleEl = document.getElementById('excel-loading-title');
      const subEl = document.getElementById('excel-loading-subtitle');
      if (titleEl) titleEl.textContent = 'Connecting to Zoho Creator REST API...';
      if (subEl) subEl.textContent = 'Fetching record ID: ' + recordId + ' from report All_Personal_Infos';

      try {
        const resp = await fetch('/api/zoho/fetch-record?record_id=' + encodeURIComponent(recordId));
        const res = await resp.json();

        if (res.success && res.data) {
          populateExcelReviewForm(res.data);
          
          // Show Zoho Creator Banner
          const banner = document.getElementById('zoho-creator-banner');
          if (banner) {
            banner.classList.remove('hidden');
            const tpName = ((res.data.taxpayer?.first_name || '') + ' ' + (res.data.taxpayer?.last_name || '')).trim() || 'Client';
            document.getElementById('zoho-banner-record-info').textContent = 
              `Taxpayer: ${tpName} | Record ID: ${recordId}`;
          }
          
          showExcelSection('review');
        } else if (res.needs_auth) {
          showExcelSection('upload');
          updateExcelStep(1);
          openZohoConfigModal(res.error || 'Zoho OAuth Access Token required.');
        } else {
          alert('Failed to load Zoho Creator record: ' + (res.error || 'Unknown error'));
          resetExcelUpload();
        }
      } catch (err) {
        alert('Network error connecting to Zoho API backend: ' + err);
        resetExcelUpload();
      }
    }

    function refreshZohoRecord() {
      if (currentCreatorRecordId) {
        initZohoCreatorMode(currentCreatorRecordId);
      }
    }

    function openZohoConfigModal(msg) {
      const modal = document.getElementById('modal-zoho-config');
      if (modal) {
        modal.classList.remove('hidden');
        if (msg) {
          document.getElementById('zoho-modal-msg').textContent = msg;
          document.getElementById('zoho-modal-msg-box').classList.remove('hidden');
        } else {
          document.getElementById('zoho-modal-msg-box').classList.add('hidden');
        }
        fetch('/api/zoho/get-config')
          .then(r => r.json())
          .then(d => {
            if (d.success && d.config) {
              const c = d.config;
              document.getElementById('zoho-input-domain').value = c.domain || 'creator.zoho.in';
              document.getElementById('zoho-input-owner').value = c.owner_name || 'zentegraindia';
              document.getElementById('zoho-input-app').value = c.app_link_name || 'drake-automation';
              document.getElementById('zoho-input-report').value = c.report_link_name || 'All_Personal_Infos';
              document.getElementById('zoho-input-token').value = c.access_token || '';
              document.getElementById('zoho-input-client-id').value = c.client_id || '';
              document.getElementById('zoho-input-client-secret').value = c.client_secret || '';
              document.getElementById('zoho-input-refresh-token').value = c.refresh_token || '';
            }
          }).catch(() => {});
      }
    }

    function closeZohoConfigModal() {
      const modal = document.getElementById('modal-zoho-config');
      if (modal) modal.classList.add('hidden');
    }

    async function saveZohoConfigForm() {
      const saveBtn = document.getElementById('btn-save-zoho-config');
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Saving...';

      const payload = {
        domain: document.getElementById('zoho-input-domain').value.trim(),
        owner_name: document.getElementById('zoho-input-owner').value.trim(),
        app_link_name: document.getElementById('zoho-input-app').value.trim(),
        report_link_name: document.getElementById('zoho-input-report').value.trim(),
        access_token: document.getElementById('zoho-input-token').value.trim(),
        client_id: document.getElementById('zoho-input-client-id').value.trim(),
        client_secret: document.getElementById('zoho-input-client-secret').value.trim(),
        refresh_token: document.getElementById('zoho-input-refresh-token').value.trim()
      };

      try {
        const resp = await fetch('/api/zoho/save-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (res.success) {
          closeZohoConfigModal();
          if (currentCreatorRecordId) {
            initZohoCreatorMode(currentCreatorRecordId);
          } else {
            alert('Zoho Creator settings saved successfully!');
          }
        } else {
          alert('Error saving config: ' + (res.error || 'Unknown error'));
        }
      } catch (err) {
        alert('Failed to save Zoho config: ' + err);
      } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Save & Continue';
      }
    }

    // Auto-load router on start
    document.addEventListener('DOMContentLoaded', () => {
      const urlParams = new URLSearchParams(window.location.search);
      const mode = urlParams.get('mode');
      const recordId = urlParams.get('record_id');

      if (mode === 'creator' && recordId) {
        initZohoCreatorMode(recordId);
      } else {
        loadPacketHistory();
      }
    });
  </script>

  <!-- ZOHO CREATOR CONFIGURATION MODAL -->
  <div id="modal-zoho-config" class="fixed inset-0 z-50 hidden bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl max-w-lg w-full border border-slate-200 shadow-2xl overflow-hidden">
      <div class="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between text-white">
        <div class="flex items-center gap-2.5">
          <i class="fa-solid fa-cloud-arrow-down text-xl"></i>
          <div>
            <h3 class="font-bold text-base">Connect Zoho Creator REST API</h3>
            <p class="text-xs text-blue-100">Fetch live records into Drake Tax 2025</p>
          </div>
        </div>
        <button onclick="closeZohoConfigModal()" class="text-white/80 hover:text-white text-lg">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>

      <div class="p-6 space-y-4 max-h-[80vh] overflow-y-auto text-xs">
        <div id="zoho-modal-msg-box" class="hidden p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-xl flex items-start gap-2">
          <i class="fa-solid fa-triangle-exclamation text-amber-500 mt-0.5"></i>
          <span id="zoho-modal-msg">Authentication required to connect with Zoho Creator.</span>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Zoho Domain</label>
            <input id="zoho-input-domain" type="text" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs" value="creator.zoho.in">
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Owner Name</label>
            <input id="zoho-input-owner" type="text" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs" value="zentegraindia">
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">App Link Name</label>
            <input id="zoho-input-app" type="text" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs" value="drake-automation">
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Report Link Name</label>
            <input id="zoho-input-report" type="text" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs" value="All_Personal_Infos">
          </div>
        </div>

        <div class="border-t border-slate-200 pt-3">
          <label class="block font-bold text-slate-900 mb-1">
            OAuth Access Token <span class="text-emerald-600 font-normal">(Fastest - 1 Hour Token)</span>
          </label>
          <input id="zoho-input-token" type="password" placeholder="Paste 1000.xxxx access token here" class="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs">
          <p class="text-[11px] text-slate-500 mt-1">Generated from <a href="https://api-console.zoho.in" target="_blank" class="text-blue-600 underline">Zoho API Console</a> (Self Client) with scope <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700">ZohoCreator.report.READ</code>.</p>
        </div>

        <div class="border-t border-slate-200 pt-3">
          <label class="block font-bold text-slate-900 mb-1">
            Permanent OAuth Setup <span class="text-slate-400 font-normal">(Optional - auto-refreshes forever)</span>
          </label>
          <div class="space-y-2 mt-1.5">
            <input id="zoho-input-client-id" type="text" placeholder="Client ID (e.g. 1000.xxx)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-xs">
            <input id="zoho-input-client-secret" type="password" placeholder="Client Secret" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-xs">
            <input id="zoho-input-refresh-token" type="password" placeholder="Refresh Token (e.g. 1000.xxx)" class="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono text-xs">
          </div>
        </div>
      </div>

      <div class="bg-slate-50 px-6 py-3 border-t border-slate-200 flex items-center justify-end gap-2">
        <button onclick="closeZohoConfigModal()" class="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-800 rounded-lg">Cancel</button>
        <button id="btn-save-zoho-config" onclick="saveZohoConfigForm()" class="px-5 py-2 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow transition">
          <i class="fa-solid fa-check mr-1"></i> Save & Continue
        </button>
      </div>
    </div>
  </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

# =============================================================================
# ZOHO CREATOR REST API INTEGRATION ENDPOINTS
# =============================================================================
@app.route("/api/zoho/fetch-record", methods=["GET"])
def api_zoho_fetch_record():
    record_id = request.args.get("record_id", "").strip()
    if not record_id:
        return jsonify({"success": False, "error": "Missing record_id parameter"}), 400
    
    data, err = zoho_api.fetch_creator_record(record_id)
    if err == "NO_TOKEN" or (err and "OAuth" in err):
        return jsonify({"success": False, "error": err, "needs_auth": True})
    if err:
        return jsonify({"success": False, "error": err})
    
    return jsonify({"success": True, "data": data, "record_id": record_id})

@app.route("/api/zoho/save-config", methods=["POST"])
def api_zoho_save_config():
    payload = request.get_json() or {}
    cfg = zoho_api.load_zoho_config()
    for k in ["domain", "owner_name", "app_link_name", "report_link_name", "client_id", "client_secret", "refresh_token", "access_token"]:
        if k in payload and payload[k] is not None:
            cfg[k] = payload[k].strip()
    if payload.get("access_token"):
        cfg["token_expiry"] = time.time() + 3500
    zoho_api.save_zoho_config(cfg)
    return jsonify({"success": True, "message": "Zoho configuration saved."})

@app.route("/api/zoho/get-config", methods=["GET"])
def api_zoho_get_config():
    cfg = zoho_api.load_zoho_config()
    masked = dict(cfg)
    if masked.get("client_secret"):
        masked["client_secret"] = masked["client_secret"][:4] + "********"
    if masked.get("refresh_token"):
        masked["refresh_token"] = masked["refresh_token"][:6] + "********"
    if masked.get("access_token"):
        masked["access_token"] = masked["access_token"][:8] + "********"
    return jsonify({"success": True, "config": masked})

# =============================================================================
# EXCEL WORKFLOW API ENDPOINTS (DEDICATED)
# =============================================================================
@app.route("/api/excel/load-sample", methods=["GET"])
def excel_load_sample():
    global active_excel_path
    sample_excel = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx"))
    active_excel_path = sample_excel
    try:
        data = extract_excel_organizer(sample_excel)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/excel/extract", methods=["POST"])
def excel_extract_file():
    global active_excel_path
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    save_path = os.path.abspath(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))
    f.save(save_path)
    active_excel_path = save_path
    try:
        data = extract_excel_organizer(save_path)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/excel/populate-drake", methods=["POST"])
def excel_populate_drake():
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        # Standardize all dates to Drake Tax format (MM/DD/YYYY)
        if "taxpayer" in data and isinstance(data["taxpayer"], dict) and "dob" in data["taxpayer"]:
            data["taxpayer"]["dob"] = format_to_drake_date(data["taxpayer"]["dob"])
        if "spouse" in data and isinstance(data["spouse"], dict) and "dob" in data["spouse"]:
            data["spouse"]["dob"] = format_to_drake_date(data["spouse"]["dob"])
        if "dependents" in data and isinstance(data["dependents"], list):
            for dep in data["dependents"]:
                if isinstance(dep, dict) and "dob" in dep:
                    dep["dob"] = format_to_drake_date(dep["dob"])

        result = populate_excel_return(data)
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "POPULATED" if success else "ERROR"
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/excel/verify-and-save", methods=["POST"])
def excel_verify_and_save():
    try:
        result = save_and_exit_excel()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "SAVED" if success else "ERROR"
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/excel/discard", methods=["POST"])
def excel_discard():
    try:
        result = discard_excel()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "DISCARDED"
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"]})

# =============================================================================
# PDF WORKFLOW API ENDPOINTS (DEDICATED)
# =============================================================================
@app.route("/api/packet/history", methods=["GET"])
def packet_history_list():
    try:
        items = history_mgr.get_history_list()
        return jsonify({"success": True, "history": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/history/<packet_id>", methods=["GET"])
def packet_history_get(packet_id):
    global active_pdf_path
    try:
        pdata = history_mgr.get_packet_by_id(packet_id)
        if not pdata:
            return jsonify({"success": False, "error": "Packet not found in history"}), 404
        if pdata.get("file_path") and os.path.exists(pdata["file_path"]):
            active_pdf_path = pdata["file_path"]
        return jsonify({
            "success": True,
            "is_packet": True,
            "packet_id": pdata.get("id"),
            "filename": pdata.get("filename"),
            "taxpayer_name": pdata.get("taxpayer_name"),
            "total_pages": pdata.get("total_pages", 1),
            "total_modules": pdata.get("total_modules", len(pdata.get("modules", []))),
            "category_counts": pdata.get("category_counts", {}),
            "modules": pdata.get("modules", []),
            "data": pdata.get("modules", [{}])[0] if pdata.get("modules") else {}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/history/<packet_id>", methods=["DELETE"])
def packet_history_delete(packet_id):
    try:
        ok = history_mgr.delete_packet_history(packet_id)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/load-sample", methods=["GET"])
def load_sample():
    global active_pdf_path
    sample_pdf = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads", "Weaver-Cummings_2025_Tax_Packet.pdf"))
    if not os.path.exists(sample_pdf):
        sample_pdf = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Weaver-Cummings_2025_Tax_Packet.pdf"))
    active_pdf_path = sample_pdf

    # Check if pre-cached in history for instant 0ms load
    h_items = history_mgr.get_history_list()
    for it in h_items:
        if it.get("filename") == "Weaver-Cummings_2025_Tax_Packet.pdf":
            pdata = history_mgr.get_packet_by_id(it["id"])
            if pdata and pdata.get("modules"):
                return jsonify({
                    "success": True,
                    "is_packet": True,
                    "packet_id": pdata["id"],
                    "filename": pdata["filename"],
                    "taxpayer_name": pdata.get("taxpayer_name"),
                    "total_pages": pdata["total_pages"],
                    "total_modules": pdata["total_modules"],
                    "category_counts": pdata["category_counts"],
                    "modules": pdata["modules"],
                    "data": pdata["modules"][0]
                })

    try:
        packet_res = extract_all_modules_from_packet(sample_pdf)
        if packet_res.get("total_modules", 0) > 0:
            saved = history_mgr.save_packet_history("Weaver-Cummings_2025_Tax_Packet.pdf", sample_pdf, packet_res)
            return jsonify({
                "success": True,
                "is_packet": True,
                "packet_id": saved["id"],
                "filename": saved["filename"],
                "taxpayer_name": saved.get("taxpayer_name"),
                "total_pages": packet_res["total_pages"],
                "total_modules": packet_res["total_modules"],
                "category_counts": packet_res["category_counts"],
                "modules": packet_res["modules"],
                "data": packet_res["modules"][0]
            })
        data = extract_w2_from_pdf(sample_pdf)
        return jsonify({"success": True, "is_packet": False, "data": data})
    except Exception as e:
        try:
            data = extract_w2_from_pdf(sample_pdf)
            return jsonify({"success": True, "is_packet": False, "data": data})
        except Exception as e2:
            return jsonify({"success": False, "error": str(e2)}), 500

@app.route("/api/extract", methods=["POST"])
def extract_file():
    global active_pdf_path
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    save_path = os.path.abspath(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))
    f.save(save_path)
    active_pdf_path = save_path
    try:
        packet_res = extract_all_modules_from_packet(save_path)
        if packet_res.get("total_modules", 0) > 0:
            saved = history_mgr.save_packet_history(f.filename, save_path, packet_res)
            return jsonify({
                "success": True,
                "is_packet": True,
                "packet_id": saved["id"],
                "filename": saved["filename"],
                "taxpayer_name": saved.get("taxpayer_name"),
                "total_pages": packet_res["total_pages"],
                "total_modules": packet_res["total_modules"],
                "category_counts": packet_res["category_counts"],
                "modules": packet_res["modules"],
                "data": packet_res["modules"][0]
            })
        data = extract_w2_from_pdf(save_path)
        return jsonify({"success": True, "is_packet": False, "data": data})
    except Exception as e:
        try:
            data = extract_w2_from_pdf(save_path)
            return jsonify({"success": True, "is_packet": False, "data": data})
        except Exception as e2:
            return jsonify({"success": False, "error": str(e2)}), 500

@app.route("/api/packet/populate-all", methods=["POST"])
def populate_all_packet():
    try:
        req_data = request.json or {}
        modules = req_data.get("modules", [])
        if not modules:
            return jsonify({"success": False, "error": "No modules provided"}), 400
        success, logs, status = populate_all_packet_modules(modules)
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/packet/populate-single", methods=["POST"])
def populate_single_packet():
    try:
        req_data = request.json or {}
        module = req_data.get("module")
        if not module:
            return jsonify({"success": False, "error": "No module provided"}), 400
        success, logs, status = populate_single_packet_module(module)
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/pdf-preview", methods=["GET"])
def pdf_preview():
    global active_pdf_path
    if active_pdf_path and os.path.exists(active_pdf_path):
        return send_file(active_pdf_path, mimetype="application/pdf", as_attachment=False)
    return "No PDF available", 404

@app.route("/api/populate-drake", methods=["POST"])
@app.route("/api/approve-and-send", methods=["POST"])
def populate_drake():
    try:
        approved_data = request.json
        if not approved_data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        result = populate_w2_screen(approved_data)
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        elif isinstance(result, tuple) and len(result) == 2:
            success, logs = result
            status = "POPULATED" if success else "ERROR"
        else:
            success = bool(result)
            logs = ["[OK] Execution complete."]
            status = "POPULATED" if success else "ERROR"

        err_msg = ""
        if not success and logs:
            err_msg = logs[-1]
        return jsonify({"success": success, "status": status, "logs": logs, "error": err_msg})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/verify-and-save", methods=["POST"])
def verify_and_save():
    try:
        result = save_and_exit_packet_screen()
        if not (isinstance(result, tuple) and result[0]):
            result = save_and_exit_w2()

        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        elif isinstance(result, tuple) and len(result) == 2:
            success, logs = result
            status = "SAVED" if success else "ERROR"
        else:
            success = bool(result)
            logs = ["[OK] Save complete."]
            status = "SAVED" if success else "ERROR"

        err_msg = ""
        if not success and logs:
            err_msg = logs[-1]
        return jsonify({"success": success, "status": status, "logs": logs, "error": err_msg})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/discard-screen", methods=["POST"])
def discard_screen():
    try:
        result = discard_w2_screen()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "DISCARDED"
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[TAXFLOW UI] Server running at: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
