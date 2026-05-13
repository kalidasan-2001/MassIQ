# MassIQ MVP — Testing Checklist

Use this checklist to validate the MVP is stable and ready for production testing.

## Pre-Flight Checks

- [ ] Backend `requirements.txt` contains: fastapi, uvicorn, python-multipart, pymupdf, openpyxl, pydantic (NO paddleocr)
- [ ] Frontend `package.json` has dependencies: react, react-dom, vite, axios (no extra libraries)
- [ ] All files created without errors (check terminal output)
- [ ] No TypeScript errors in IDE (only JavaScript)

## Backend Startup

```bash
cd massiq-mvp/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- [ ] Backend starts on `http://127.0.0.1:8000`
- [ ] Console shows "Application startup complete"
- [ ] Directories created: `app/storage/uploads/`, `app/storage/rendered_pages/`, `app/storage/exports/`

### Test Backend Health

```bash
curl http://127.0.0.1:8000/
# Should return: {"status":"ok","message":"MassIQ backend running"}
```

- [ ] GET `/` returns 200 with status: ok

## Frontend Startup

```bash
cd massiq-mvp/frontend
npm install
npm run dev
```

- [ ] Frontend starts on `http://localhost:5173/`
- [ ] Console shows "VITE ready in Xms"
- [ ] Page loads with title "MassIQ — MVP"

## End-to-End Workflow Test

### 1. Upload PDF

1. [ ] Download or prepare a sample PDF floor plan
2. [ ] Click file input, select PDF
3. [ ] Click "Upload PDF"
4. [ ] Wait for upload/render (may take 5-10 sec)
5. [ ] Verify:
   - File uploads without error
   - Image appears on screen
   - `file_id` shown (e.g., `a1b2c3d4e5f6g7h8`)
   - Browser network tab shows 200 response from `/upload-pdf`

### 2. Calibration

1. [ ] Page should show "Step 1: Calibrate Scale" section
2. [ ] Image should have crosshair cursor
3. [ ] Click two distinct points on the plan (e.g., opposite corners)
   - [ ] Red dot #1 appears at first click
   - [ ] Red dot #2 appears at second click
   - [ ] Points should be clearly separated
4. [ ] Enter real distance in meters (e.g., `10.5` for 10.5m)
5. [ ] Click "Calculate Scale"
6. [ ] Verify:
   - [ ] Green checkmark appears: "✓ Scale: X.XX px/m"
   - [ ] "Step 2: Draw Polygon" section becomes active (clickable)

**Expected**: Scale value should be reasonable (e.g., 50-500 px/m depending on PDF resolution)

### 3. Polygon Drawing

1. [ ] Must have completed calibration first
2. [ ] Click to mark polygon vertices (minimum 3 points)
   - [ ] Blue dots appear at each click
   - [ ] Vertices count increases: "Vertices: 1", "Vertices: 2", etc.
3. [ ] After 3+ clicks, "Close Polygon" button becomes enabled
4. [ ] Click "Close Polygon"
5. [ ] Verify:
   - [ ] Green checkmark appears: "✓ Area: X.XXXX m² (Y px²)"
   - [ ] Polygon highlights on image with blue outline
   - [ ] "Step 3: Calculate Volume" section becomes active

**Expected**: Polygon should visually outline the component; area should be > 0

### 4. Component & Volume

1. [ ] Component name prefilled with "Stahlbeton C25/30" (editable)
2. [ ] Enter Height/Thickness (e.g., `0.3` for 30cm)
3. [ ] Click "Calculate Volume"
4. [ ] Verify result table appears:
   - [ ] Component name column correct
   - [ ] Area (m²) showing 4 decimals (e.g., `12.3456`)
   - [ ] Height (m) showing 3 decimals (e.g., `0.300`)
   - [ ] Volume (m³) showing 4 decimals (e.g., `3.7037`)

**Expected**: Volume = Area × Height; numbers properly formatted

### 5. Export to Excel

1. [ ] Result table visible with "Export to Excel" button
2. [ ] Click "Export to Excel"
3. [ ] Verify:
   - [ ] Browser downloads: `ProjectName_quantities.xlsx`
   - [ ] Success message: "✓ Excel exported successfully!"
   - [ ] No error messages
4. [ ] Open downloaded Excel file:
   - [ ] Row 1/A1: Project name visible
   - [ ] Row 3: Headers (Component | Area (m²) | Height (m) | Volume (m³))
   - [ ] Row 4: Data matches onscreen result
   - [ ] Numbers properly formatted (rounded)

**Expected**: Excel file valid and readable; values match UI

### 6. Data Persistence (localStorage Test)

1. [ ] Complete full workflow (steps 1-5)
2. [ ] Browser DevTools → Application → Local Storage → http://localhost:5173
   - [ ] Key visible: `massiq-project-{file_id}`
   - [ ] Value contains JSON with all state
3. [ ] Reload page (F5 or Ctrl+R)
4. [ ] Verify:
   - [ ] Image still visible (from cache)
   - [ ] All previously entered data restored:
     - [ ] Project name
     - [ ] Scale value
     - [ ] Polygon vertices
     - [ ] Component name and height
     - [ ] Result table

**Expected**: No data loss on page reload

## Validation & Error Handling Tests

### Test Wrong-Order Clicking

1. [ ] Upload PDF, DON'T calibrate
2. [ ] Try to click on image to draw polygon
   - [ ] Should NOT draw polygon (mode still calibrate)
   - [ ] No crash or console error
3. [ ] Try to "Close Polygon" without drawing
   - [ ] Button should be disabled (grayed out)
   - [ ] Click should do nothing
4. [ ] Try to "Calculate Volume" without completing steps
   - [ ] Button should be functional but show error message in red
   - [ ] Message should say what's missing (e.g., "Calibrate scale first")

**Expected**: App never crashes; clear error messages guide user

### Test Input Validation

1. [ ] Calibration with distance = 0 or negative
   - [ ] Should show error: "Enter a distance > 0"
   - [ ] Scale should not be set
2. [ ] Calibration with distance = empty
   - [ ] Should show error: "Enter a distance > 0"
3. [ ] Volume height = 0
   - [ ] Should show error: "Enter height > 0"
4. [ ] Export without project name
   - [ ] Button should be disabled or show validation error
5. [ ] Export without component name
   - [ ] Should show error before attempting export

**Expected**: All validations work; no silent failures

### Test Reset Buttons

1. [ ] After calibration, click "Reset" in Step 1
   - [ ] [ ] Points and scale cleared
   - [ ] [ ] Can re-calibrate with different points
2. [ ] After drawing polygon, click "↻ Reset All & Start Over"
   - [ ] [ ] All data cleared (scale, polygon, component, height, result)
   - [ ] [ ] Workflow resets to Step 1: Calibrate
   - [ ] [ ] localStorage updated

**Expected**: Fresh start possible without page reload

## Browser/Environment Tests

- [ ] **Chrome/Edge**: Test upload, rendering, export
- [ ] **Firefox**: Test upload, rendering, export
- [ ] **Safari** (if available): Test upload, rendering, export
- [ ] **Responsive**: Test on different screen sizes (F12 → Responsive Design Mode)
  - [ ] [ ] Desktop (1920×1080)
  - [ ] [ ] Tablet (768×1024)
  - [ ] [ ] Mobile (375×667)

**Expected**: Works consistently across browsers; responsive layout

## Performance Tests

- [ ] PDF upload time < 10 seconds (include rendering)
- [ ] Polygon drawing responsive (no lag on 100+ vertices)
- [ ] Export generation < 2 seconds
- [ ] Page reload with restored state < 1 second

## Console & Logging

- [ ] Browser console (F12 → Console) clean
  - [ ] [ ] No JavaScript errors (red)
  - [ ] [ ] No warnings for MVP (yellow OK; deprecation warnings acceptable)
- [ ] Backend console shows logging
  - [ ] [ ] INFO logs for uploads, renders, exports
  - [ ] [ ] No error flags (ERROR logs only for actual failures)

### Example Expected Backend Logs

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
INFO:     File uploaded successfully: a1b2c3d4
INFO:     PDF uploaded and rendered: a1b2c3d4
INFO:     Excel exported: e5f6g7h8 for file a1b2c3d4
```

## Test Scenarios

### Scenario 1: Simple Rectangle Measurement
- Upload floor plan with known rectangle (e.g., 10m × 5m room)
- Calibrate with ruler or grid
- Draw polygon around room
- Verify area ≈ 50 m²
- Set height = 2.8m (ceiling)
- Export and verify volume ≈ 140 m³

### Scenario 2: Complex Component
- Measure multi-vertex beam or column base
- Calibrate from known scale on plan
- Draw polygon with 8+ vertices
- Enter exact height measurement
- Export to Excel

### Scenario 3: Multiple Attempts
- Do full workflow first time
- Reset all
- Do second measurement (different component)
- Verify localStorage updated correctly

## Known Limitations (Document for Next Version)

- [ ] Single component per export (can measure multiple, but export one at a time)
- [ ] No PDF annotation (drawings not saved to PDF)
- [ ] No multi-page support (first page only)
- [ ] No undo for individual polygon vertices
- [ ] No zoom on large images
- [ ] No authentication (local storage only)

## Sign-Off

**Tester Name:** ________________  
**Date:** ________________  
**Build Version:** 0.1.0-MVP  
**Overall Status:** PASS / FAIL  

**Issues Found:**
- [ ] None
- [ ] See GitHub issues #___, #___, #___

**Sign-Off:** Once all checks pass, this MVP is approved for:
- [ ] Internal testing
- [ ] Client demonstration
- [ ] Production deployment (with caveats documented above)

