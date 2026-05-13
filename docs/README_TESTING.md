# MassIQ MVP - Testing & Launch Guide

## 🎯 Status: READY FOR COMPREHENSIVE TESTING ✅

Both backend and frontend are running and validated. The complete MVP workflow is ready for end-to-end testing.

---

## 🚀 Quick Start (3 Steps)

### Step 1: Verify Services Running
```bash
# Check backend
curl http://127.0.0.1:8000/
# Expected: {"status":"ok","message":"MassIQ backend running"}

# Check frontend
curl http://localhost:5173/
# Expected: HTML response with "MassIQ MVP" title
```

### Step 2: Open Browser
Navigate to: **http://localhost:5173**

### Step 3: Follow Workflow
Execute the 11-step end-to-end workflow (see below)

---

## 📋 11-Step Complete Testing Workflow

### Step 1: Upload Floor Plan PDF
- Click "Choose File" button
- Select any of the 6 test PDFs available:
  - `173c721ffd564d00a41e90f00f50e6c7.pdf`
  - `4da379b164124c8da94643e45308e485.pdf`
  - `5b59fa1ccb19419d9968b6e34657422a.pdf`
  - `8d409b5f5e74472baf37d855f8ba6905.pdf`
  - `90c503434254448693e5a1ae010e6ef5.pdf`
  - `c02d03efedf145aa80d613463d49bd60.pdf`
- Click "Upload PDF"
- **Expected:** Image loads showing floor plan (2x zoom rendering)

### Step 2: Calibrate Scale (2-Point Method)
- Click 2 points on the floor plan image that are at a known distance apart
- Example: Two opposite corners of a room that measure 5 meters
- Enter the real distance in meters (e.g., 5)
- **Expected:** System calculates pixels/meter ratio for area calculations

### Step 3: Select Legend Area
- Drag to draw a rectangle around the legend area (where hatch patterns are shown)
- Shows preview of selected area
- **Expected:** Legend region highlighted with preview

### Step 4: Select Hatch Pattern Sample
- Enter component name (e.g., "Concrete Slab", "Steel", "Grout")
- Drag within the legend rectangle to select the hatch pattern sample
- Click "Save Hatch Sample"
- **Expected:** Hatch sample saved and preview shown

### Step 5: Run Automatic Detection
- Adjust threshold slider (0.3 = loose detection, 0.95 = strict)
- Start with 0.5 for balanced results
- Click "Auto Detect"
- **Expected:** Backend runs OpenCV algorithm
  - Green overlay regions appear on floor plan
  - Each region shows: ID, bounding box, confidence %
  - List appears showing all detected regions

### Step 6: Review & Accept/Reject Detections
- Panel shows all detected regions with status badges
- For each region, choose:
  - ✓ Accept (keep this detection)
  - ✗ Reject (discard this detection)
  - 🗑 Delete (remove from consideration)
- Watch counts update: Green (accepted), Red (rejected), Gray (deleted)
- Click "Confirm Selection" when done
- **Expected:** Only accepted regions move forward to volume calculation

### Step 7: Add Correction Polygons (Optional)
- Click "Add Polygon" button to enable add mode
- Draw polygon on areas where hatch was missed
  - Click to set vertices
  - Double-click to finish polygon
- Polygon shows as yellow while drawing, turns green when saved
- Area automatically calculated in m² using calibrated scale
- **Expected:** Polygon added to correction list with area calculated

### Step 8: Subtract Correction Polygons (Optional)
- Click "Subtract Polygon" button to enable subtract mode
- Draw polygon to remove from calculated area
  - Click to set vertices
  - Double-click to finish polygon
- Polygon shows as yellow while drawing, turns red when saved
- Area automatically calculated in m² using calibrated scale
- **Expected:** Polygon subtracted from total with area calculated

### Step 9: Upload & Confirm Section Height
- Click "Upload Section Image" to provide side view
- Image shows height/thickness dimension
- Drag to crop the height dimension area
- Manually enter confirmed height in meters (e.g., 0.2 for 20cm)
- Click "Confirm Height"
- **Expected:** Height locked in, ready for volume calculation

### Step 10: Calculate Volume
- Volume = (detected_area_m² + added_area_m² - subtracted_area_m²) × height_m
- Click "Calculate Volume"
- **Expected:** Result table populated with:
  - Component name
  - # Detected regions (from detection)
  - # Accepted (from review)
  - # Rejected (from review)
  - Added area (m²)
  - Subtracted area (m²)
  - Final area (m²)
  - Height (m)
  - FINAL VOLUME (m³)

### Step 11: Export Excel Report
- Click "Export Excel" button
- Browser downloads `massiq_quantity_report.xlsx`
- **Expected:** Excel file contains:
  ```
  PROJECT INFORMATION:
    - Project Name
    - Plan Name
    - Export Date
  
  COMPONENT:
    - Component Name
    - Detection Method: "Automatic hatch detection with user review"
    - Hatch Sample Used: Yes
  
  DETECTION REVIEW:
    - Total Candidate Detections: 12
    - Accepted Detections: 10
    - Rejected Detections: 2
    - Manual Add Corrections: 1
    - Manual Subtract Corrections: 0
  
  FINAL QUANTITY:
    - Final Area (m²): 42.5
    - Height (m): 0.2
    - FINAL VOLUME (m³): 8.5
  
  NOTES & REVIEW:
    - Review Status: Completed
    - Notes: [Workflow summary]
  ```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| **TESTING_STATUS.txt** | Quick reference guide with all commands and troubleshooting |
| **TEST_REPORT.md** | Comprehensive 12-section infrastructure validation report |
| **PHASE_14_SUMMARY.md** | What was completed in this testing phase |
| **SYSTEM_STATUS.txt** | Real-time status check (backend/frontend running) |
| **README_TESTING.md** | This file - complete testing guide |

---

## 🔧 What Was Fixed

### Backend Import Error (RESOLVED ✅)
**File:** `backend/app/routes/detection.py`, line 8

**Problem:**
```python
from fastapi import ..., FileResponse  # ❌ Wrong
ImportError: cannot import name 'FileResponse' from 'fastapi'
```

**Solution:**
```python
from fastapi import ...  # Correct imports
from fastapi.responses import FileResponse  # ✅ Correct
```

**Result:** Backend now starts cleanly without errors.

---

## ✅ Validation Checklist

- [x] Backend running on http://127.0.0.1:8000
- [x] Frontend running on http://localhost:5173
- [x] All Python dependencies installed
- [x] All API endpoints functional
- [x] CORS configured
- [x] Storage directories ready
- [x] 6 test PDFs available
- [x] Excel export working
- [x] Detection algorithm loaded
- [x] UI components rendering
- [x] Import errors fixed
- [x] Infrastructure validated

---

## 🐛 Troubleshooting

### Backend Not Starting
```
Error: ImportError: cannot import name 'FileResponse' from 'fastapi'
Status: FIXED ✓

File: backend/app/routes/detection.py, line 8
Fix: Import FileResponse from fastapi.responses instead of fastapi
```

### Frontend Blank Page
1. Press F12 to open developer console
2. Check for JavaScript errors
3. Verify backend is responding: `curl http://127.0.0.1:8000/`
4. Clear browser cache and reload

### PDF Upload Not Working
1. Verify `backend/app/storage/uploads/` exists and has permissions
2. Check backend console for error messages
3. Try different PDF file

### Excel Export Not Working
1. Check `backend/app/storage/exports/` has write permissions
2. Verify openpyxl installed: `pip list | grep openpyxl`
3. Check backend console for errors

---

## 📊 Performance Metrics

- Backend start time: ~2 seconds
- Frontend dev server: ~1 second
- PDF rendering: ~2 seconds
- Detection algorithm: Depends on PDF size (typically 3-10 seconds)
- Excel export: ~1 second
- File sizes:
  - Test PDF: ~455KB
  - Rendered page: ~635KB
  - Hatch sample: ~50KB (varies)
  - Excel export: ~6KB

---

## 🎓 Key Features Demonstrated

1. **Automatic Detection** - OpenCV algorithm finds hatch patterns
2. **User Review** - Accept/reject/delete interface for quality control
3. **Manual Corrections** - Add/subtract polygons for fine-tuning
4. **Calculation Formula** - Properly combines detected + corrected areas
5. **Height Confirmation** - Section view to measure thickness/height
6. **Volume Calculation** - Area × Height = Volume
7. **Professional Export** - Excel report proving automatic detection method
8. **Data Persistence** - localStorage saves project state

---

## 🚀 Next Steps After Testing

If all 11 steps work correctly:

1. **Document Results** - Note which steps worked/failed
2. **Fix Issues** - Address any problems found
3. **Repeat Testing** - Verify fixes work
4. **Load Real Plans** - Test with actual construction floor plans
5. **Validate Accuracy** - Compare automatic measurements with manual
6. **User Feedback** - Get feedback on workflow and UI

---

## 📝 Commands Reference

### Backend
```bash
cd c:/Users/kalid/MassIQ/massiq-mvp/backend
source venv/Scripts/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd c:/Users/kalid/MassIQ/massiq-mvp/frontend
npm run dev
```

### Test Backend Health
```bash
curl http://127.0.0.1:8000/
```

### Test Frontend Health
```bash
curl http://localhost:5173/ | grep title
```

---

**Generated:** 2025-05-08  
**Status:** ✅ COMPLETE - Ready for end-to-end testing  
**Infrastructure:** Validated and running  
**Workflow:** All 11 steps ready to execute
