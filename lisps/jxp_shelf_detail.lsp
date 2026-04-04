;;; ================================================================
;;; JXP_SHELF_DETAIL.LSP
;;; JXP Architecture | Organo Antharam Office Interior
;;; Director Cabin — Shelving Unit Detail
;;;
;;; USAGE:
;;;   Command: JXPSHELF     → draws the full shelving detail
;;;   Command: JXPSHELF-CLR → erases previous CABIN-SHELF-* content
;;;
;;; DIMENSIONS: all in mm, drawn 1:1 in model space
;;; All [TBC] dims are placeholders — confirm with client before issue
;;; ================================================================

;;; ---- UTILITY: layer create/switch ----
(defun JXP-LAYER (nm col ltype / )
  (if (not (tblsearch "LAYER" nm))
    (command "_.LAYER" "_N" nm "")
  )
  (command "_.LAYER" "_C" (itoa col) nm "_LT" ltype nm "")
  (princ)
)

(defun JXP-SET (nm / ) (command "_.LAYER" "_S" nm "") (princ))

;;; ---- UTILITY: draw closed rectangle as lightweight polyline ----
(defun JXP-RECT (x1 y1 x2 y2 / )
  (command "_.RECTANG" (list x1 y1) (list x2 y2))
)

;;; ---- UTILITY: hatch a rectangular region by internal midpoint ----
;;;   Call AFTER setting HPNAME / HPSCALE / HPANG via setvars
(defun JXP-HATCH-RECT (x1 y1 x2 y2 pat scl ang / mx my)
  (setvar "HPNAME"  pat)
  (setvar "HPSCALE" scl)
  (setvar "HPANG"   ang)
  (setq mx (* 0.5 (+ x1 x2)))
  (setq my (* 0.5 (+ y1 y2)))
  ;; Draw the boundary rectangle first on current layer
  (JXP-RECT x1 y1 x2 y2)
  ;; Pick interior point — AutoCAD detects the polyline boundary
  (command "_.HATCH" (list mx my) "")
  (princ)
)

;;; ---- UTILITY: single-line text (bottom-left anchor) ----
(defun JXP-TXT (x y h str / )
  (command "_.TEXT" (list x y) h 0 str)
)

;;; ---- UTILITY: linear dimension, horizontal or vertical ----
(defun JXP-DIMH (x1 y1 x2 y2 yd override / )
  ;; Horizontal dim between (x1,y1) and (x2,y2), placed at y = yd
  (command "_.DIMLINEAR" (list x1 y1) (list x2 y2) (list (* 0.5 (+ x1 x2)) yd) override)
)
(defun JXP-DIMV (x1 y1 x2 y2 xd override / )
  ;; Vertical dim, placed at x = xd
  (command "_.DIMLINEAR" (list x1 y1) (list x2 y2) (list xd (* 0.5 (+ y1 y2))) override)
)

;;; ---- UTILITY: erase all entities on a named layer ----
(defun JXP-ERASE-LAYER (nm / ss)
  (setq ss (ssget "_X" (list (cons 8 nm))))
  (if ss (command "_.ERASE" ss "") (princ (strcat "\n  (no entities on " nm ")")))
  (princ)
)

;;; ================================================================
;;; COMMAND: JXPSHELF-CLR — clear previous shelving detail content
;;; ================================================================
(defun c:JXPSHELF-CLR ( / layers nm)
  (setq layers (list
    "CABIN-SHELF-STEEL"
    "CABIN-SHELF-STONE"
    "CABIN-SHELF-VENEER"
    "CABIN-SHELF-HATCH"
    "CABIN-SHELF-DIMS"
    "CABIN-SHELF-NOTES"
    "CABIN-SHELF-TITLE"
    "CABIN-SHELF-CLOUD"
    "OPEN-QUESTIONS"
  ))
  (princ "\n[JXP] Clearing previous shelving detail entities...")
  (foreach nm layers (JXP-ERASE-LAYER nm))
  (princ "\n[JXP] Clear complete. Run JXPSHELF to rebuild.")
  (princ)
)

;;; ================================================================
;;; COMMAND: JXPSHELF — main drawing routine
;;; ================================================================
(defun c:JXPSHELF ( /
  ;; ---- dimensions (mm, all TBC unless noted) ----
  SW        ; shelf width (left-right in elevation)
  ST        ; shelf structural thickness (steel box incl. stone top+bot)
  SD        ; shelf depth, front-to-back (in section view)
  SNT       ; stone cladding thickness (all faces)
  CG        ; clear gap between shelf 1 and shelf 2
  BG        ; bottom gap (below lower shelf in elevation)
  TG        ; top gap (above upper shelf in elevation)
  EH        ; total elevation height (computed)
  ;; ---- elevation origin ----
  ox oy
  ;; ---- shelf Y coords (relative to oy) ----
  s1b s1t   ; shelf 1 bottom / top
  s2b s2t   ; shelf 2 bottom / top
  ;; ---- cut Y ----
  cutY
  ;; ---- section origin ----
  sx sy
  ;; ---- keynote box ----
  kx ky kw kh
  ;; ---- dim style backup/restore ----
  old-dimtxt old-dimasz old-dimclrd old-dimclrt
)

  ;; ==============================================================
  ;; 0. DIMENSIONS — change these to update the whole drawing
  ;; ==============================================================
  (setq SW    1200.0)   ; shelf width                    [TBC]
  (setq ST      80.0)   ; shelf thickness (incl. stone)  [TBC]
  (setq SD     400.0)   ; shelf depth front-to-back      [TBC]
  (setq SNT     20.0)   ; stone cladding thickness        [TBC]
  (setq CG     400.0)   ; clear gap between shelves       [TBC]
  (setq BG     150.0)   ; bottom gap in elevation
  (setq TG     150.0)   ; top gap in elevation

  ;; derived
  (setq EH  (+ BG ST CG ST TG))   ; = 980mm total elevation height

  ;; elevation origin (model space)
  (setq ox 0.0  oy 0.0)

  ;; shelf vertical positions (Y from oy)
  (setq s1b (+ oy BG))
  (setq s1t (+ s1b ST))
  (setq s2b (+ s1t CG))
  (setq s2t (+ s2b ST))

  ;; section A-A cut line at mid of shelf 1
  (setq cutY (+ s1b (* 0.5 ST)))

  ;; section view origin — well right of elevation
  (setq sx (+ ox SW 350.0))
  (setq sy (+ oy (- (/ EH 2.0) (/ SD 2.0))))   ; vertically centred against elevation

  ;; keynote box — right of section
  (setq kx (+ sx SD 180.0))
  (setq ky (+ oy EH))
  (setq kw 400.0)
  (setq kh 320.0)

  ;; ==============================================================
  ;; 1. LAYER SETUP  (JXP standards: color / linetype)
  ;; ==============================================================
  (princ "\n[JXP] 1/8  Setting up layers...")
  ;;                   name                   ACI  linetype
  (JXP-LAYER "CABIN-SHELF-TITLE"              7   "Continuous")
  (JXP-LAYER "CABIN-SHELF-STONE"              7   "Continuous")   ; white  0.30
  (JXP-LAYER "CABIN-SHELF-STEEL"              1   "Continuous")   ; red    0.18
  (JXP-LAYER "CABIN-SHELF-VENEER"             2   "Continuous")   ; yellow 0.25
  (JXP-LAYER "CABIN-SHELF-HATCH"              8   "Continuous")   ; grey
  (JXP-LAYER "CABIN-SHELF-DIMS"               3   "Continuous")   ; green  0.15
  (JXP-LAYER "CABIN-SHELF-NOTES"              6   "Continuous")   ; magenta 0.10
  (JXP-LAYER "CABIN-SHELF-CLOUD"              1   "Continuous")
  (JXP-LAYER "OPEN-QUESTIONS"                 6   "Phantom")

  ;; ==============================================================
  ;; 2. DIMENSION STYLE — match JXP standards
  ;; ==============================================================
  (setq old-dimtxt  (getvar "DIMTXT"))
  (setq old-dimasz  (getvar "DIMASZ"))
  (setq old-dimclrd (getvar "DIMCLRD"))
  (setq old-dimclrt (getvar "DIMCLRT"))
  (setvar "DIMTXT"   3.0)    ; text 3mm — match title block notes height
  (setvar "DIMASZ"   2.0)    ; arrow 2mm
  (setvar "DIMCLRD"  3)      ; green
  (setvar "DIMCLRT"  3)      ; green
  (setvar "DIMCLRE"  3)      ; green
  (setvar "DIMEXO"   1.5)    ; extension line offset
  (setvar "DIMGAP"   1.0)    ; dim line gap

  ;; ==============================================================
  ;; 3. DRAWING TITLES & NOTES
  ;; ==============================================================
  (princ "\n[JXP] 2/8  Drawing titles & notes...")
  (JXP-SET "CABIN-SHELF-TITLE")

  ;; Main title
  (JXP-TXT ox (+ oy EH 90)  10  "DIRECTOR CABIN — SHELVING UNIT DETAIL")
  (JXP-TXT ox (+ oy EH 74)   5  "Project: Organo Antharam Office Interior")
  (JXP-TXT ox (+ oy EH 64)   5  "Ref: Meeting — Director cabin shelving with stone cladding")

  ;; Construction notes
  (JXP-SET "CABIN-SHELF-NOTES")
  (JXP-TXT ox (+ oy EH 48)   3.5  "NOTE: Stone shelf and steel shelf start + end at same levels (TYP.)")
  (JXP-TXT ox (+ oy EH 40)   3.5  "Full stone cladding on all 4 faces of stone shelf — adhesive + mech. anchor fixing")
  (JXP-TXT ox (+ oy EH 32)   3.5  "SHELF 1 (LOWER) = SHELF 2 (UPPER) — Two equal shelves (dims TBC)")

  ;; Elevation sub-title
  (JXP-SET "CABIN-SHELF-TITLE")
  (JXP-TXT (+ ox (* 0.5 SW)) (+ oy EH 16) 5 "FRONT ELEVATION  |  Scale 1:10  |  ALL DIMS IN mm")

  ;; ==============================================================
  ;; 4. FRONT ELEVATION — WALL REFERENCE & FRAME
  ;; ==============================================================
  (princ "\n[JXP] 3/8  Drawing front elevation...")

  ;; Wall backing line (right edge)
  (JXP-SET "CABIN-SHELF-STONE")
  (command "_.LINE" (list (+ ox SW 10) (- oy 20)) (list (+ ox SW 10) (+ oy EH 10)) "")

  ;; Floor reference line (thin)
  (JXP-SET "CABIN-SHELF-DIMS")
  (command "_.LINE" (list (- ox 60) oy) (list (+ ox SW 60) oy) "")

  ;; ---- SHELF 1 (LOWER) ----
  ;; Outer stone boundary (heavy outline on STONE layer)
  (JXP-SET "CABIN-SHELF-STONE")
  (JXP-RECT ox s1b (+ ox SW) s1t)

  ;; Inner steel frame (lighter, on STEEL layer)
  (JXP-SET "CABIN-SHELF-STEEL")
  (JXP-RECT (+ ox SNT) (+ s1b SNT)
            (- (+ ox SW) SNT) (- s1t SNT))

  ;; ---- SHELF 2 (UPPER) ----
  (JXP-SET "CABIN-SHELF-STONE")
  (JXP-RECT ox s2b (+ ox SW) s2t)

  (JXP-SET "CABIN-SHELF-STEEL")
  (JXP-RECT (+ ox SNT) (+ s2b SNT)
            (- (+ ox SW) SNT) (- s2t SNT))

  ;; ---- SHELF LEVEL ALIGNMENT TICK MARKS (left side) ----
  ;;   Stone shelf start = Steel shelf start — key design requirement
  (JXP-SET "CABIN-SHELF-DIMS")
  (foreach yv (list s1b s1t s2b s2t)
    (command "_.LINE" (list (- ox 45) yv) (list (- ox 5) yv) "")   ; tick left
    (command "_.LINE" (list (+ ox SW 5) yv) (list (+ ox SW 45) yv) "") ; tick right
  )

  ;; Shelf labels
  (JXP-SET "CABIN-SHELF-NOTES")
  (JXP-TXT (- ox 55) (+ s1b 3) 3 "1")
  (JXP-TXT (- ox 55) (+ s2b 3) 3 "2")

  ;; ==============================================================
  ;; 5. HATCHING — ELEVATION
  ;; ==============================================================
  (princ "\n[JXP] 4/8  Hatching elevation...")
  (JXP-SET "CABIN-SHELF-HATCH")

  ;; Stone strips — Shelf 1
  ;;   Bottom strip
  (JXP-HATCH-RECT ox s1b (+ ox SW) (+ s1b SNT) "AR-SAND" 0.3 0)
  ;;   Top strip
  (JXP-HATCH-RECT ox (- s1t SNT) (+ ox SW) s1t "AR-SAND" 0.3 0)
  ;;   Left strip (between stone strips)
  (JXP-HATCH-RECT ox (+ s1b SNT) (+ ox SNT) (- s1t SNT) "AR-SAND" 0.3 0)
  ;;   Right strip
  (JXP-HATCH-RECT (- (+ ox SW) SNT) (+ s1b SNT) (+ ox SW) (- s1t SNT) "AR-SAND" 0.3 0)
  ;;   Steel core — cross hatch
  (JXP-HATCH-RECT (+ ox SNT) (+ s1b SNT) (- (+ ox SW) SNT) (- s1t SNT) "ANSI31" 30 45)

  ;; Stone strips — Shelf 2 (identical pattern, offset by (s2b-s1b))
  (JXP-HATCH-RECT ox s2b (+ ox SW) (+ s2b SNT) "AR-SAND" 0.3 0)
  (JXP-HATCH-RECT ox (- s2t SNT) (+ ox SW) s2t "AR-SAND" 0.3 0)
  (JXP-HATCH-RECT ox (+ s2b SNT) (+ ox SNT) (- s2t SNT) "AR-SAND" 0.3 0)
  (JXP-HATCH-RECT (- (+ ox SW) SNT) (+ s2b SNT) (+ ox SW) (- s2t SNT) "AR-SAND" 0.3 0)
  (JXP-HATCH-RECT (+ ox SNT) (+ s2b SNT) (- (+ ox SW) SNT) (- s2t SNT) "ANSI31" 30 45)

  ;; ==============================================================
  ;; 6. ELEVATION DIMENSIONS
  ;; ==============================================================
  (princ "\n[JXP] 5/8  Adding elevation dimensions...")
  (JXP-SET "CABIN-SHELF-DIMS")

  ;; Width — below elevation
  (JXP-DIMH ox s1b (+ ox SW) s1b (- oy 70) (strcat "W = " (rtos SW 2 0) " [TBC]"))

  ;; Shelf 1 thickness — right side
  (JXP-DIMV (+ ox SW) s1b (+ ox SW) s1t (+ ox SW 90)
             (strcat "t = " (rtos ST 2 0) " [TBC]"))

  ;; Clear gap between shelves — right side
  (JXP-DIMV (+ ox SW) s1t (+ ox SW) s2b (+ ox SW 90)
             (strcat "~" (rtos CG 2 0) " CLEAR [TBC]"))

  ;; Shelf 2 thickness — right side
  (JXP-DIMV (+ ox SW) s2b (+ ox SW) s2t (+ ox SW 90)
             (strcat "t = " (rtos ST 2 0) " [TBC]"))

  ;; Overall elevation height — left side
  (JXP-DIMV ox s1b ox s2t (- ox 120)
             (strcat "H = " (rtos (- s2t s1b) 2 0) " [TBC]"))

  ;; Stone cladding call-out (left, shelf 1 bottom strip)
  (command "_.LEADER"
    (list (+ ox (/ SW 4.0)) (+ s1b (/ SNT 2.0)))   ; arrow tip (mid of stone strip)
    (list (- ox 80) (- s1b 30))                      ; leader elbow
    (list (- ox 80) (- s1b 30))                      ; endpoint
    ""
    (strcat "STONE t=" (rtos SNT 2 0) " [TBC] (TYP.)")
    ""
  )

  ;; Section cut line A-A
  (JXP-SET "CABIN-SHELF-DIMS")
  (command "_.LINE" (list (- ox 50) cutY) (list (+ ox SW 50) cutY) "")
  ;; Section marks at each end
  (JXP-TXT (- ox 70) (+ cutY 6)  4.5  "A")
  (JXP-TXT (+ ox SW 55) (+ cutY 6) 4.5 "A")
  ;; Arrow indicators
  (command "_.LINE" (list (- ox 55) (+ cutY 12)) (list (- ox 45) cutY) "")
  (command "_.LINE" (list (- ox 55) (- cutY 12)) (list (- ox 45) cutY) "")
  (command "_.LINE" (list (+ ox SW 55) (+ cutY 12)) (list (+ ox SW 45) cutY) "")
  (command "_.LINE" (list (+ ox SW 55) (- cutY 12)) (list (+ ox SW 45) cutY) "")

  ;; ==============================================================
  ;; 7. SECTION A-A — HORIZONTAL SECTION THROUGH SHELF 1
  ;; ==============================================================
  (princ "\n[JXP] 6/8  Drawing Section A-A...")

  ;; Section title
  (JXP-SET "CABIN-SHELF-TITLE")
  (JXP-TXT sx (+ sy SD 60) 5 "SECTION A-A  [Scale 1:10]")

  ;; "FRONT OF SHELF" / "BACK / WALL FACE" column headers
  (JXP-SET "CABIN-SHELF-NOTES")
  (JXP-TXT (- sx 5) (+ sy SD 44) 3 "FRONT OF SHELF")
  (JXP-TXT (+ sx SW 5) (+ sy SD 44) 3 "BACK / WALL FACE")
  ;; note: SW used here as plan width = SW (same 1200mm), depth is SD
  ;; but section width = SW and section height = SD (rotated view)
  ;; Let's use SD as horizontal (front-to-back) and SW_sec as vertical portion shown

  ;; Because SW = 1200 is very large for a section box, show a representative 600mm portion
  (setq SWsec 600.0)   ; portion of shelf width shown in section

  ;; --- Section outer stone box ---
  (JXP-SET "CABIN-SHELF-STONE")
  (JXP-RECT sx sy (+ sx SD) (+ sy SWsec))          ; front-to-back × portion of width

  ;; --- Section inner steel frame ---
  (JXP-SET "CABIN-SHELF-STEEL")
  (JXP-RECT (+ sx SNT) (+ sy SNT)
            (- (+ sx SD) SNT) (- (+ sy SWsec) SNT))

  ;; --- Section labels ---
  (JXP-SET "CABIN-SHELF-NOTES")
  ;; Front face label (left side of section box)
  (command "_.TEXT" "_J" "_BC" (list sx (+ sy SWsec 30)) 3 0
    "FRONT FACE")
  ;; Wall face label (right side)
  (command "_.TEXT" "_J" "_BC" (list (+ sx SD) (+ sy SWsec 30)) 3 0
    "WALL FACE")
  ;; "FULL SHELF WIDTH = 1200 [TBC] — SECTION SHOWS PORTION" note
  (JXP-TXT sx (- sy 35) 2.8
    (strcat "NOTE: Full shelf W=" (rtos SW 2 0) " [TBC] — section shows " (rtos SWsec 2 0) " portion"))

  ;; --- Section hatching ---
  (JXP-SET "CABIN-SHELF-HATCH")
  ;; Stone: 4 strips
  ;;   Front face strip (left)
  (JXP-HATCH-RECT sx sy (+ sx SNT) (+ sy SWsec) "AR-SAND" 0.3 0)
  ;;   Back face strip (right)
  (JXP-HATCH-RECT (- (+ sx SD) SNT) sy (+ sx SD) (+ sy SWsec) "AR-SAND" 0.3 0)
  ;;   Side strip (bottom in plan)
  (JXP-HATCH-RECT (+ sx SNT) sy (- (+ sx SD) SNT) (+ sy SNT) "AR-SAND" 0.3 0)
  ;;   Side strip (top in plan)
  (JXP-HATCH-RECT (+ sx SNT) (- (+ sy SWsec) SNT) (- (+ sx SD) SNT) (+ sy SWsec) "AR-SAND" 0.3 0)
  ;;   Steel core
  (JXP-HATCH-RECT (+ sx SNT) (+ sy SNT) (- (+ sx SD) SNT) (- (+ sy SWsec) SNT) "ANSI31" 30 45)

  ;; --- Section dimensions ---
  (JXP-SET "CABIN-SHELF-DIMS")
  ;; Overall depth (front to back) — below section
  (JXP-DIMH sx sy (+ sx SD) sy (- sy 60)
             (strcat "D = " (rtos SD 2 0) " [TBC]"))
  ;; Stone thickness — front face (left), using vertical dim
  (JXP-DIMH sx sy (+ sx SNT) sy (- sy 35)
             (strcat "t=" (rtos SNT 2 0)))
  ;; Stone thickness — back face (right)
  (JXP-DIMH (- (+ sx SD) SNT) sy (+ sx SD) sy (- sy 35)
             (strcat "t=" (rtos SNT 2 0)))
  ;; Shelf portion width — right of section
  (JXP-DIMV (+ sx SD) sy (+ sx SD) (+ sy SWsec) (+ sx SD 80)
             (strcat (rtos SWsec 2 0) " (PORTION)"))

  ;; Anchor & adhesive leaders
  (JXP-SET "CABIN-SHELF-NOTES")
  (command "_.LEADER"
    (list (+ sx (* 0.5 SD)) (+ sy (* 0.5 SWsec)))   ; arrow tip = centre of steel core
    (list (+ sx SD 120) (+ sy (* 0.5 SWsec)))
    (list (+ sx SD 120) (+ sy (* 0.5 SWsec)))
    ""
    "MS STEEL FRAME (PWD-CTD TO MATCH)"
    ""
  )
  (command "_.LEADER"
    (list (+ sx (* 0.25 SD)) (+ sy (+ SNT (* 0.3 SWsec))))  ; in stone strip area
    (list (+ sx SD 120) (+ sy (* 0.3 SWsec)))
    (list (+ sx SD 120) (+ sy (* 0.3 SWsec)))
    ""
    "STONE CLADDING — ADH. BED + M6 ANCHOR @ 400 c/c"
    ""
  )

  ;; ==============================================================
  ;; 8. MATERIAL KEYNOTES BOX
  ;; ==============================================================
  (princ "\n[JXP] 7/8  Drawing material keynotes box...")

  (setq kx (+ sx SD 120))    ; align with section leaders
  (setq ky (+ oy EH))

  ;; Box border
  (JXP-SET "CABIN-SHELF-TITLE")
  (JXP-RECT kx (- ky kh) (+ kx kw) ky)

  ;; Title bar
  (command "_.LINE" (list kx (- ky 22)) (list (+ kx kw) (- ky 22)) "")
  (JXP-TXT (+ kx 8) (- ky 8) 4.5 "MATERIAL KEYNOTES:")

  ;; Keynote entries
  (JXP-SET "CABIN-SHELF-NOTES")
  (JXP-TXT (+ kx 8) (- ky 34)  3.2 "1  Green marble — as per client selection")
  (JXP-TXT (+ kx 16) (- ky 44) 3.2 "(confirm marble spec + finish with client)")
  (JXP-TXT (+ kx 8) (- ky 59)  3.2 "2  Green stained veneer — as per client selection")
  (JXP-TXT (+ kx 8) (- ky 74)  3.2 "3  MS steel frame — powder coated to match")
  (JXP-TXT (+ kx 8) (- ky 89)  3.2 "4  Adhesive bed + M6 mech. anchor @ 400 c/c (TYP.)")
  (JXP-TXT (+ kx 8) (- ky 104) 3.2 "5  Stone cladding t = ~20mm on ALL 4 faces")

  ;; Divider
  (JXP-SET "CABIN-SHELF-TITLE")
  (command "_.LINE" (list kx (- ky 116)) (list (+ kx kw) (- ky 116)) "")

  ;; Open questions section
  (JXP-SET "OPEN-QUESTIONS")
  (JXP-TXT (+ kx 8) (- ky 126) 4 "!! OPEN QUESTION !!")
  (JXP-SET "CABIN-SHELF-NOTES")
  (JXP-TXT (+ kx 8) (- ky 142) 2.8 "Exact shelf dimensions NOT confirmed in meeting.")
  (JXP-TXT (+ kx 8) (- ky 152) 2.8 "Placeholder dims shown — verify with client:")
  (JXP-TXT (+ kx 8) (- ky 164) 2.8 (strcat "W  = ~" (rtos SW  2 0) " mm  [TBC]"))
  (JXP-TXT (+ kx 8) (- ky 174) 2.8 (strcat "t  = ~" (rtos ST  2 0) " mm  [TBC]"))
  (JXP-TXT (+ kx 8) (- ky 184) 2.8 (strcat "D  = ~" (rtos SD  2 0) " mm  [TBC]"))
  (JXP-TXT (+ kx 8) (- ky 194) 2.8 (strcat "Gap= ~" (rtos CG  2 0) " mm  [TBC]"))
  (JXP-TXT (+ kx 8) (- ky 204) 2.8 (strcat "Stone t= ~" (rtos SNT 2 0) " mm  [TBC]"))

  ;; ==============================================================
  ;; 9. RESTORE DIM STYLE & ZOOM
  ;; ==============================================================
  (setvar "DIMTXT"  old-dimtxt)
  (setvar "DIMASZ"  old-dimasz)
  (setvar "DIMCLRD" old-dimclrd)
  (setvar "DIMCLRT" old-dimclrt)

  (command "_.ZOOM" "_E")

  ;; ==============================================================
  ;; 10. SUMMARY REPORT
  ;; ==============================================================
  (princ "\n")
  (princ "\n[JXP] =====================================================")
  (princ "\n[JXP] DIRECTOR CABIN SHELVING DETAIL — COMPLETE")
  (princ "\n[JXP] =====================================================")
  (princ (strcat "\n[JXP]  Front elevation:  W=" (rtos SW 2 0) " x H=" (rtos EH 2 0) " mm"))
  (princ (strcat "\n[JXP]  Shelf 1:  Y=" (rtos s1b 2 0) " to " (rtos s1t 2 0)))
  (princ (strcat "\n[JXP]  Shelf 2:  Y=" (rtos s2b 2 0) " to " (rtos s2t 2 0)))
  (princ (strcat "\n[JXP]  Section A-A at Y=" (rtos cutY 2 0) " (mid of shelf 1)"))
  (princ "\n[JXP]  ALL [TBC] DIMENSIONS REQUIRE CLIENT CONFIRMATION")
  (princ "\n[JXP] =====================================================")
  (princ "\n[JXP] NOTE: If hatches did not render, run _HATCH manually")
  (princ "\n[JXP]       using pattern AR-SAND/ANSI31 on stone/steel areas.")
  (princ)
)

;;; End of JXP_SHELF_DETAIL.LSP
