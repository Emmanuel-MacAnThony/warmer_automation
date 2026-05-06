# HITL System Implementation - 3 Phase Plan

**Goal**: Build Human-in-the-Loop system for natural agent interactions
**Principle**: Simplicity over complexity

---

## Phase 1: Core HITL Infrastructure 🏗️

**What We're Building**: The foundation that all use cases will use

### Backend (`backend/hitl/`)
- [x] Create `core.py` - Centralized HITL engine
  - `HITLCore` class with checkpoint/resume logic
  - `wait_for_user_input()` - Generic pause mechanism
  - `receive_user_input()` - Handle user responses
  - Simple in-memory state storage (dict)

### Frontend (`chrome-extension/hitl/`)
- [x] Create `panel-manager.js` - Panel injection & lifecycle
  - `showPanel(type, data)` - Inject panel into DOM
  - `hidePanel()` - Remove panel
  - `registerPanelRenderer(type, renderer)` - Panel registry
- [x] Create `styles/panels.css` - Shared panel styles
  - Base panel container styles
  - Button styles
  - Form element styles

### Validation
- [x] Create simple "approval" test panel
- [x] Backend sends panel → Frontend displays → User clicks → Backend receives
- [x] Test pause/resume flow works end-to-end

**Deliverables**:
- Basic HITL infrastructure working
- Test panel proving the concept
- ~200 lines of backend code
- ~150 lines of frontend code

---

## Phase 2: Field Mapping Use Case 🗺️

**What We're Building**: First real use case - LinkedIn to Airtable field mapping

### Backend (`backend/hitl/`)
- [x] Create `field_mapping.py` - Field mapping logic
  - `FieldMappingHITL` class
  - `get_mapping_config()` - Main entry point
  - `_auto_detect_mappings()` - Simple rule-based matching (exact name match, fuzzy match)
  - `_validate_mapping()` - Ensure valid configuration

### Backend (`backend/tools/`)
- [x] Update `airtable_tool.py` - Add schema fetching
  - `get_base_schema()` - Get available fields from Airtable
  - Cache schema per base/table

### Frontend (`chrome-extension/hitl/panels/`)
- [x] Create `field-mapping-panel.js` - Field mapping UI
  - Render checkboxes (enable/disable fields)
  - Render dropdowns (select source field)
  - Render overwrite toggle (empty only vs always)
  - Save/Cancel buttons
  - localStorage integration for saved configs

### Integration
- [x] Update enrichment agent to use field mapping HITL
  - First time: Show panel → Get config → Save to localStorage
  - Subsequent: Use saved config
  - Allow "Change mapping" command to re-show panel

**Deliverables**:
- Working field mapping panel
- Episodic memory (remembers per base/table)
- Selective field updates working
- ~300 lines of backend code
- ~250 lines of frontend code

---

## Phase 3: PDF Export & Lead Review 📄

**What We're Building**: PDF downloads + peopleAlsoViewed lead review

### Backend (`backend/utils/`)
- [x] Create `pdf_generator.py` - PDF export functionality
  - `generate_search_results_pdf()` - Convert search results to PDF
  - Use `reportlab` library (simple, no dependencies)
  - Include: Profile data, search metadata, timestamp

### Backend (`backend/hitl/`)
- [x] Create `lead_review.py` - Lead review use case
  - `LeadReviewHITL` class
  - `get_selected_leads()` - Show peopleAlsoViewed panel
  - Return user-selected leads to enrich

### Frontend (`chrome-extension/hitl/panels/`)
- [x] Create `lead-review-panel.js` - Lead selection UI
  - Display peopleAlsoViewed profiles as cards
  - Checkboxes to select which to enrich
  - Preview profile info (name, company, title)
  - "Select All" / "Deselect All" helpers

### Frontend (`chrome-extension/`)
- [x] Add PDF download button to chat interface
  - Shows after enrichment completes
  - Downloads PDF of enriched data
  - Clear visual feedback

**Deliverables**:
- PDF export working
- Lead review panel functional
- Complete HITL system ready for production
- ~200 lines of backend code
- ~200 lines of frontend code

---

## Technology Choices (Keep It Simple)

**Backend**:
- No database - Use in-memory dicts for state (can add Redis later if needed)
- `reportlab` for PDF (simple, pure Python)
- Standard library wherever possible

**Frontend**:
- Vanilla JS (no framework overhead)
- CSS variables for theming (already have)
- localStorage for persistence (no IndexedDB complexity)

**Communication**:
- Extend existing WebSocket/HTTP pattern
- Add `type: 'show_panel'` message type
- Add `type: 'user_input'` message type

---

## Success Criteria Per Phase

### Phase 1 ✓
- [ ] Can pause agent execution
- [ ] Can show panel to user
- [ ] Can receive user response
- [ ] Can resume agent execution
- [ ] Test panel works end-to-end

### Phase 2 ✓
- [ ] Field mapping panel displays correctly
- [ ] Can enable/disable fields
- [ ] Can change field sources
- [ ] Config saves to localStorage
- [ ] Subsequent enrichments use saved config
- [ ] Can modify saved config

### Phase 3 ✓
- [ ] PDF generates correctly with profile data
- [ ] PDF downloads in browser
- [ ] Lead review panel shows peopleAlsoViewed
- [ ] Can select/deselect leads
- [ ] Selected leads get enriched
- [ ] All error cases handled gracefully

---

## Estimated Timeline

- **Phase 1**: 2-3 hours (foundation)
- **Phase 2**: 3-4 hours (main feature)
- **Phase 3**: 2-3 hours (polish)

**Total**: ~8-10 hours of focused implementation

---

## Notes

- After each phase: Review, test, approve before continuing
- Keep commits small and focused
- Add comments for non-obvious logic
- Test with real LinkedIn/Airtable data
- Handle errors gracefully (show user-friendly messages)

---

**LET'S BUILD! 🚀**
