> **Shared across every project** (ba-tools `skills/figma-build/references/plugin-gotchas.md`).
> Merged 2026-09-24 from Acme Lending's `figma-plugin-api-gotchas.md` (sections 0–4 below) and NWE's
> operational notes (section 5). A trap found on any project goes here, once, for everyone.
> Product-specific traps (a named component that misbehaves) go in that product's design profile.

# Figma `use_figma` gotchas — Claude/MCP context

Quick-reference index for scripts run via `mcp__plugin_product-management_figma__use_figma`. Grep by operation keyword before writing scripts.

**Authoritative source:** [figma/mcp-server-guide `SKILL.md`](https://github.com/figma/mcp-server-guide/blob/main/skills/figma-use/SKILL.md). When this file disagrees with the SKILL.md, trust the SKILL.md.

**History note (2026-05-18):** several gotchas in this file were originally workarounds for symptoms caused by **incorrect script structure** (wrapping in `(async () => { ... })()`). After reading the canonical SKILL.md, those workarounds were removed and the actual rule documented. The sentinel-rectangle readback pattern, for example, was a workaround for `return` values not surfacing — which was caused by the IIFE wrap, not a real MCP limitation.

---

## 0. Required script structure — read this first

These rules come straight from the SKILL.md. Violating them produces silent failures or thrown errors.

### 0.1 No outer `(async () => { ... })()` wrapper

**The runtime auto-wraps your code in an async context with top-level `await` and `return` already enabled.** Wrapping it yourself breaks return-value capture — your `return` statement never reaches the MCP server, so the tool response is `"code executed with no return value"` regardless of what you returned.

```javascript
// ✗ WRONG — silently breaks returns
(async () => {
  const x = await figma.getNodeByIdAsync("...");
  return { x };  // never surfaces
})();

// ✓ RIGHT — top-level await + return work directly
const x = await figma.getNodeByIdAsync("...");
return { x };  // returns as JSON to the MCP server
```

### 0.2 Return structured data

`use_figma` JSON-serializes the return value. Return an object with:
- `createdNodeIds: [...]` — every node your script created
- `mutatedNodeIds: [...]` — every node you modified
- `counts`, `errors`, `stage`, or any other state useful for verification

Don't rely on sentinel rectangles to read back state — use `return` directly.

### 0.3 Maximum ~10 logical operations per call

A "logical operation" = create node + set properties + parent it. For more than ~20 nodes, split across multiple `use_figma` calls. Build top-down with placeholder frames, then populate children in subsequent calls. Verify between calls with `get_metadata` (structure) or `get_screenshot` (visual).

**Empirically observed:** at ~150+ node creations in one script, the script terminates silently (likely the 30s MCP transport timeout). The official ceiling of ~10 logical ops is the safe budget.

### 0.4 Forbidden APIs

| API | What happens | Use instead |
|---|---|---|
| `figma.notify(...)` | Throws `"not implemented"` | `return` |
| `figma.closePlugin()` | Throws | (just `return` — runtime handles cleanup) |
| `console.log(...)` for output | Doesn't surface to MCP | `return` |
| `figma.currentPage = page` (sync setter) | Throws `"Setting figma.currentPage is not supported"` | `await figma.setCurrentPageAsync(page)` |
| `figma.loadAllPagesAsync()` | Throws `"loadAllPagesAsync is not a supported API"` | Per-page `await figma.setCurrentPageAsync(page)` |
| `getPluginData()` / `setPluginData()` | Not supported | `getSharedPluginData()` / `setSharedPluginData()` |

### 0.5 Error recovery is atomic

`use_figma` script execution is atomic — failed scripts do not commit partial changes (provided your script follows the structure rules in 0.1–0.4). On error:

1. **STOP.** Don't immediately retry.
2. Read the error message.
3. If unclear, call `get_metadata` or `get_screenshot` to inspect current state.
4. Fix the script.
5. Retry the corrected script.

---

## 1. Quick index (one-liner per gotcha)

| # | Operation keyword | One-liner | Source |
|---|---|---|---|
| G1 | structure | No IIFE wrap — top-level `await` and `return` are implicit | SKILL.md §0 |
| G2 | structure | Max ~10 logical ops per call; chunk larger work | SKILL.md §0 |
| G3 | structure | Use `return { createdNodeIds, mutatedNodeIds, ... }` — not sentinel rectangles | SKILL.md §0 |
| G4 | cross-page | `figma.currentPage` resets to first page at the start of every call | SKILL.md §8 |
| G5 | cross-page | `getNodeByIdAsync` resolves only after `setCurrentPageAsync(page)` for that page | SKILL.md §8 + empirical |
| G6 | cross-page | `loadAllPagesAsync` is unsupported here | SKILL.md §0 |
| G7 | cross-page | `page.children.length` reads 0 for unloaded pages — call `setCurrentPageAsync` first | empirical 2026-05-18 |
| G8 | clone | ⚠️ Cloned nodes parent under **`figma.currentPage`** (which resets to the FIRST page each call — G4), NOT the source's page. ALWAYS `targetPage.appendChild(clone)` + reset x/y + verify parent page | empirical 2026-07-04 (corrected) |
| G9 | clone | Cloned cells inherit auto-layout from source — `cell.layoutMode = "NONE"` before manual positioning | empirical 2026-05-18 |
| G10 | clone | `instance.swapComponent(c)` preserves position + dimensions + id | empirical |
| G11 | clone | `instance.detachInstance()` returns the new FRAME synchronously; old id becomes invalid | empirical |
| G12 | clone | Component property defIds survive `importComponentByKeyAsync`; `setProperties` works on imports | empirical |
| G13 | font | Load font with `await figma.loadFontAsync(fontName)` BEFORE setting `characters` | SKILL.md §6 |
| G14 | font | Verify font styles with `await figma.listAvailableFontsAsync()` — `"SemiBold"` vs `"Semi Bold"` is a common typo | SKILL.md §6 |
| G15 | text | Set `textAutoResize` BEFORE setting `characters`; don't call `.resize()` on text nodes directly | SKILL.md §6 + empirical |
| G16 | layout | `resize()` BEFORE setting `layoutSizingHorizontal/Vertical`; resize resets sizing modes to FIXED | SKILL.md §5 |
| G17 | layout | `layoutSizingHorizontal/Vertical = 'FILL'` MUST be set AFTER `parent.appendChild(child)` | SKILL.md §5 |
| G18 | layout | Modern: `figma.createAutoLayout(direction, props)` instead of manual frame + layoutMode | SKILL.md §10 |
| G19 | layout | Frame resize cascades to STRETCH-constrained children — usually intended for wide-mode | empirical 2026-05-14 |
| G20 | layout | Reverting the cascade fails silently on auto-layout containers; resize root back to revert | empirical 2026-05-14 |
| G21 | svg | `set_vectorPaths` requires space-separated tokens — `M16 3` works, `M163` fails | empirical 2026-05-14 |
| G22 | svg | `set_vectorPaths` supports only M, L, Z reliably; **C and Q may fail as first command** | Figma forum |
| G23 | svg | Multiple `M...L...M...L...` subpaths in one `data` string render as a connected polygon — use separate VECTOR nodes | empirical 2026-05-13 |
| G24 | svg | Multi-node icons can show cropping artifacts despite `clipsContent=false` — wrap each stroke in its own minimal VECTOR | empirical 2026-05-13 |
| G25 | svg | `figma.createNodeFromSvg(svgString)` is the most robust path — handles full SVG including C curves | empirical 2026-05-18 |
| G26 | color | Color range is 0–1, not 0–255. `{r: 1, g: 0, b: 0}` is red | SKILL.md §7 |
| G27 | color | Paint shape is `{type, color: {r,g,b}, opacity}` — opacity at paint level, NOT in color | SKILL.md §7 |
| G28 | color | `fills` / `strokes` are read-only arrays — clone, modify, reassign; never mutate in place | SKILL.md §7 |
| G29 | color | `setBoundVariableForPaint` returns a NEW paint object — capture and reassign to the node | SKILL.md §7 |
| G30 | variable | Always set `variable.scopes` explicitly — default `ALL_SCOPES` pollutes every picker | SKILL.md §9 |
| G31 | variable | `lineHeight` / `letterSpacing` require `{unit, value}` shape, not bare numbers | research |
| G32 | traverse | `node.children` THROWS on non-container types (RECTANGLE, VECTOR, ELLIPSE, TEXT) | empirical 2026-05-14 |
| G33 | traverse | Modern: `node.query('TEXT[name=Title]')` CSS-selector shorthand replaces verbose findAll loops | SKILL.md §14 |
| G34 | traverse | Modern: `node.set({ opacity: 0.5, cornerRadius: 8, name: "Card" })` batch updates | SKILL.md §14 |
| G35 | traverse | Modern: `await node.screenshot({ scale: 2 })` inline (saves a separate `get_screenshot` call) | SKILL.md §14 |
| G36 | promise | Every async call must be `await`ed — unawaited promises cause silent races | SKILL.md §12 |
| G37 | library | `setSharedPluginData` namespace must be alphanumeric / `_` / `.` — hyphens reject | empirical 2026-05-13 |
| G38 | library | Library subscriptions are per-file; parallel-library files need their own subscriptions added via Figma UI | empirical 2026-05-13 |
| G39 | platform | Windows-native Figma MCP has known connection flakiness — see [claude-code#5125](https://github.com/anthropics/claude-code/issues/5125) | research |
| G40 | icons | **Never `createNodeFromSvg` for icons that exist as library components.** Find a sample instance, `await inst.getMainComponentAsync()`, then `mainComponent.createInstance()` for each replacement | empirical 2026-05-18 |
| G41 | icons | `importComponentByKeyAsync(key)` may throw "not found" for keys captured from existing instances if the subscription is partial — the `createInstance()` route via a same-file sample is the reliable workaround | empirical 2026-05-18 |
| G42 | icons | Phosphor icon instances render with default fill `color/text-primary` (black-100) via a bound variable. To recolor (e.g. primary-aqua), traverse to the inner VECTOR child and override `fills` directly — instance-level override breaks the variable binding cleanly | empirical 2026-05-18 |
| G44 | icons | "Canonical" isn't only COMPONENTs — bundled-SVG icons (e.g. Xero brand mark imported from svgrepo) live as plain top-level FRAMEs and won't show up in INSTANCE-only searches. After zero `INSTANCE` hits, also scan FRAME/GROUP/VECTOR by name; clone the source FRAME (`source.clone()`) instead of falling back to `createNodeFromSvg` | empirical 2026-05-18 |
| G46 | variants | `instance.setProperties({Foo: "x"})` silently no-ops when `"x"` isn't in the variant set — no error, no change. Probe `mainComponent.parent.variantGroupProperties[Foo].values` first | empirical 2026-05-19 |
| G47 | text | Mixed inline-format text (e.g. "BOLD WORDS regular tail…") that needs to wrap to the parent's left edge must be ONE TEXT node with `setRangeFontName(start, end, font)`, NOT separate TEXT children in auto-layout — separate children create hanging indents on wrap | empirical 2026-05-19 |
| G48 | rotation | Figma `node.rotation` is POSITIVE = COUNTERCLOCKWISE; CSS `transform: rotate()` is POSITIVE = CLOCKWISE. Mirror the SIGN when porting CSS `-rotate-90` → Figma `rotation = 90`. Easy to verify visually with any directional icon (caret, chevron, arrow) | empirical 2026-05-20 |
| G49 | layout | New auto-layout FRAMEs inherit FIXED 100×100 dimensions until you explicitly set both `primaryAxisSizingMode` AND `counterAxisSizingMode`. Setting only one axis leaves the other at FIXED, baking the 100px default into the layout — observed on inline chips, "rightSide" amount+pct frames inside Leaderboard / TopPayoffs / TopPayouts rows that ended up 100 tall instead of HUG (~20). **Always set both axes** | empirical 2026-05-20 |
| G50 | dash | `dashPattern` is a STROKE property, not a FILL property. Setting `rectangle.dashPattern = [4,4]` on a fill-only rectangle does NOT render dashed — the fill is solid regardless. Use `figma.createLine()` (stroke-only node), or set the property on a frame's `strokeWeight + strokes + dashPattern` together. Observed when porting CSS `border-t border-dashed` styles | empirical 2026-05-20 |
| G51 | layout | Setting `frame.layoutMode` on an existing FIXED-sized frame implicitly flips BOTH `primaryAxisSizingMode` AND `counterAxisSizingMode` back to AUTO, undoing the FIXED that `resize()` set per G16. Symptom: "rounded-full elements render as pills" because the frame HUG-shrinks to fit its child content after the layoutMode setter fires. Distinct from G16 (resize→layoutSizing) and G49 (newly-created auto-layout frames). Workaround: order matters — `layoutMode` FIRST, then re-lock `primaryAxisSizingMode = "FIXED"` AND `counterAxisSizingMode = "FIXED"`, then `resize(w, h)`, then `cornerRadius` | empirical 2026-05-22 (S7 v93 fix-pass 2) |
| G52 | text | `resize()` on a TEXT node silently RESETS `textAutoResize` to `NONE` (sibling of G16). So `t.textAutoResize="HEIGHT"; t.resize(w,10); t.characters=…` leaves the text a fixed 10px box — it wraps at width `w` but the height never grows, so it renders one clipped line / overflows and `t.height` reads 10. Fix: order is create → `t.resize(w, 10)` → `t.textAutoResize="HEIGHT"` → load font → `t.characters=…`. For a **fixed-width wrapping chat bubble**: build the wrapped TEXT this way in one `use_figma` call, then in the NEXT call read the now-settled `t.height` and draw/size the bubble rectangle behind it (measure-then-layout across two calls) — reading `t.height` in the same call that sets `characters` returns the stale pre-wrap value | empirical 2026-07-21 (Penny widget 1.2 chat bubbles) |
| G53 | query | `node.findOne(...)` / `findAll(...)` can abort the WHOLE script with `TypeError: in findOne: unsupported type in createVMObject: NONE` when the subtree holds a node the sandbox can't marshal — and the abort ROLLS BACK every mutation in that call, so a page + clone created earlier in the same script silently vanish (looks like the call "did nothing"). Don't use `findOne`/`findAll` for traversal in this file; use a manual stack walk (`const s=[root]; while(s.length){const n=s.pop(); if(pred(n)) return n; if('children' in n) for(const c of n.children) s.push(c);}`), which handles the same subtrees fine | empirical 2026-08-07 (Quick note concept — cloning the Application-history drawer) |
| G54 | layout | A cloned frame's children may be positioned by an auto-layout parent you didn't notice, so `child.x = …` is silently ignored. Symptom: a badge appended to a `SPACE_BETWEEN` header row snaps to the far right whatever x you assign, colliding with the control already there. Check `parent.layoutMode` BEFORE positioning; to sit two elements together inside an auto-layout row, wrap them in their own HUG horizontal frame and `insertChild(0, cluster)` instead of fighting the x | empirical 2026-08-07 (Notes heading + count badge) |
| G55 | layout | Auto-width on a TEXT (`textAutoResize='WIDTH_AND_HEIGHT'`) does NOT stop clipping while an ANCESTOR frame is still FIXED — the text grows and the fixed parent cuts it off. Symptom: "Lashanda Miller" rendering as "Lashanda Mille" in a cloned row whose left block was a fixed 134px. Fix the container too (`left.layoutSizingHorizontal='HUG'`, sibling `FILL`), not just the text | empirical 2026-08-07 (note rows) |
| G56 | instance | Hiding sublayers inside an INSTANCE (e.g. trimming a sidebar menu): (1) setting `visible=false` **replaces the node** — any ref you hold, even the one you just hid, throws "node … does not exist" on the next read, so capture names first and re-find from the instance root (`getNodeByIdAsync(instanceId)`) for every hide; (2) hidden instance sublayers **drop out of `.children`**, so a wrapper whose only child you hid reads as `children.length === 0`; (3) wrappers often have a FIXED height and keep their gap — hide the wrapper too. Never "climb until the parent has ≥N children": it overshoots and hides the whole menu. Hide the known item level by name (EPD sidebar: FRAME `Content`), and `resetOverrides()` to undo | empirical 2026-09-25 (merchant-portal sidebar) |
| G57 | paint | A bound-variable paint keeps its **opacity only if the opacity is in the paint you bind**: `setBoundVariableForPaint({type:"SOLID",color,opacity:0.1}, "color", v)`. Spreading `{...boundPaint, opacity}` afterwards is dropped, and even a correct tint set while building a frame can come back at 1 in the same call. Set tints again in a **separate** `use_figma` call after the build and read `fills[0].opacity` back | empirical 2026-09-30 (Majordome — tinted banners and active menu rows) |
| G58 | screenshot | A `node.screenshot()` in the **same call** that changed a fill can show the old fill. When a screenshot disagrees with what you set, read the property back, then screenshot in a separate call before "fixing" anything | empirical 2026-09-30 (Majordome — CRM sidebar active row) |
| G59 | image | `upload_assets` accepts WebP, but some WebP files (e.g. the ones a CMS serves from `/thumbnail/…webp`) upload with HTTP 200 and then render **blank**: the bytes are there but `getImageByHash(h).getSizeAsync()` throws "Could not read image size from image metadata". Convert to JPEG (Pillow: `Image.open(p).convert("RGB").save(q, "JPEG", quality=85)`) and upload again to the same nodeIds. Check with `get_screenshot` (server render), not `node.screenshot()` | empirical 2026-09-30 (Majordome — photos from arthurmajordome.com) |

---

## 2. By operation type

### Script structure — `structure`

See §0 above. The top three rules (G1, G2, G3) are the most consequential. If you remember nothing else, remember:

1. Don't wrap in `(async () => { ... })()`.
2. Cap each script at ~10 logical ops.
3. Use `return` to surface results.

### Cross-page operations — `cross-page`, `getNodeByIdAsync`, `setCurrentPageAsync`

**G4. Page context resets at the start of every call.** `figma.currentPage` is always the first page at script entry. If you need to operate on another page, `await figma.setCurrentPageAsync(target)` first.

**G5. `getNodeByIdAsync` only resolves nodes on the loaded page.** Pages are lazy-loaded in this MCP context. To access a node on another page, `setCurrentPageAsync` first.

**G6. `loadAllPagesAsync()` is unsupported.** Don't call it. Use per-page `setCurrentPageAsync`.

**G7. `page.children.length` reads 0 for unloaded pages.** Don't use it as an "is empty" check across multiple pages without loading each first.

**G8. ⚠️ Cloned nodes parent under `figma.currentPage`, NOT the source's page.** (Corrected 2026-07-04 — the old claim "inherits source page" is WRONG.) Because `figma.currentPage` resets to the **first document page** at the start of every call (G4), `sourceOnPageX.clone()` lands the copy on the **first page** (e.g. `🌐 COMMON`), not on page X — even when the source lives elsewhere. This silently misplaced 3 Customers screens onto COMMON on 2026-07-04.
**Always, after cloning:** `targetPage.appendChild(clone)` → re-set `clone.x/clone.y` (page-absolute coords survive the move) → **verify**: walk `node.parent` up to the `PAGE` and assert its name. A screenshot won't catch a wrong-page placement — the frame renders fine in isolation. (To clone directly onto the target instead, `await figma.setCurrentPageAsync(targetPage)` first — note the sync setter `figma.currentPage = page` throws, see §0.4.)

Iterating all pages — recommended pattern:

```javascript
for (const page of figma.root.children) {
  await figma.setCurrentPageAsync(page);
  // page.children is populated now
}
```

### Cloning + component instances — `clone`, `setProperties`, `swapComponent`, `detachInstance`

**G9. Cloned cells inherit HORIZONTAL auto-layout.** Appending children with manual x/y positioning gets overridden — they stack horizontally. Set `cell.layoutMode = "NONE"` before appendChild for absolute positioning.

**G10. `swapComponent(newComponent)` preserves position, dimensions, and instance ID.** Only the `mainComponent` reference changes.

**G11. `detachInstance()` returns the new FRAME synchronously.** Capture the returned node. The old instance ID becomes invalid — `getNodeByIdAsync(oldId)` returns null.

**G12. Component property defIds (`Page title#11:0`) survive `importComponentByKeyAsync`.** `setProperties({...})` works on imported instances with the source file's defIds.

### Fonts + text — `font`, `text`, `characters`

**G13. Canonical text recipe** (applies to ANY font family, not just Inter):

```javascript
await figma.loadFontAsync(textNode.fontName);  // or { family, style }
textNode.characters = "...";
textNode.fontName = ...;  // if changing
```

**G14. Verify font styles with `await figma.listAvailableFontsAsync()`.** Common typo: `"SemiBold"` vs `"Semi Bold"` — the latter is correct for Inter.

**G15. Set `textAutoResize` BEFORE `characters`. Don't call `.resize()` on text nodes directly.** Calling `txt.resize(w, h)` after setting characters switches autoResize to HEIGHT, causing long text to wrap within `w`. To allow free-growth, set `textAutoResize = "WIDTH_AND_HEIGHT"` first. For fixed dimensions (e.g. for column-width layouts), use `textAutoResize = "HEIGHT"` then set characters.

### Layout, auto-layout, resize — `layout`, `resize`

**G16. `resize()` BEFORE setting layout sizing modes.** `node.resize(w, h)` resets `layoutSizingHorizontal/Vertical` to FIXED. If you want FILL or HUG, set them AFTER resize. **See also G51** — the inverse side of this rule: setting `layoutMode` AFTER `resize()` re-flips the sizing modes BACK to AUTO and undoes the FIXED that resize set, HUG-shrinking the frame.

**G17. `layoutSizingHorizontal/Vertical = 'FILL'` must be set AFTER `parent.appendChild(child)`.** Setting before throws `"node must be an auto-layout frame..."`.

**G18. Prefer `figma.createAutoLayout(direction, props)` for structured containers** instead of manual `figma.createFrame()` + `layoutMode = 'VERTICAL'`:

```javascript
// Modern
const col = figma.createAutoLayout('VERTICAL', { name: 'Column', itemSpacing: 8 });

// Manual (still works, more verbose)
const col = figma.createFrame();
col.layoutMode = 'VERTICAL';
col.itemSpacing = 8;
```

**G19. Frame resize cascades to STRETCH-constrained children.** Setting `root.resize(2080, h)` on a frame whose Content column has `constraints.horizontal === 'STRETCH'` propagates to all descendants. Usually intended for wide-mode renders.

**G20. Reverting the cascade by manually resizing children fails silently on auto-layout containers.** Cleanest revert: resize the root back to original width.

**G51. Setting `layoutMode` on an existing FIXED-sized frame implicitly flips BOTH sizing modes back to AUTO.** Distinct from G16 (resize→layoutSizing direction) and G49 (newly-created auto-layout frames). The setter `frame.layoutMode = "HORIZONTAL"` (or `"VERTICAL"`) defaults `primaryAxisSizingMode` and `counterAxisSizingMode` to `"AUTO"` — undoing the FIXED that any prior `resize(w, h)` established per G16. The frame then HUG-shrinks to fit its child content.

**Visible symptom:** "rounded-full elements render as pills." A frame `resize(40, 40)` + `cornerRadius = 20` (intended as a 40×40 circle) shrinks to roughly the text-glyph dimensions of the single digit inside it after `layoutMode = "HORIZONTAL"` fires, ending up as a ~7-10 wide × 40 tall pill — and the cornerRadius=20 applies to the new mis-shaped dimensions.

**Empirical evidence:** Session 7 v93 ApplicationWizard render fix-pass 2 (2026-05-22). 6 step circles (40×40 numbered digits) initially rendered as pills because the build script's order was `resize(40, 40)` → `cornerRadius = 20` → `layoutMode = "HORIZONTAL"` (added later to center the digit child). The layoutMode setter fired last and HUG-shrunk every circle. Fix landed in the v1.1 pattern bump commit chain.

**Correct order — choose one:**

```javascript
// Option A: set layoutMode FIRST, then re-lock sizing, then resize
circle.layoutMode = "HORIZONTAL";          // flips sizing to AUTO (default for new auto-layout)
circle.primaryAxisSizingMode = "FIXED";    // re-lock
circle.counterAxisSizingMode = "FIXED";    // re-lock
circle.resize(40, 40);
circle.cornerRadius = 20;
// add child digit AFTER — child can have layoutSizingHorizontal = "HUG" without affecting parent

// Option B (if you have already resized): re-lock sizing AFTER layoutMode
circle.resize(40, 40);
circle.layoutMode = "HORIZONTAL";          // this flips sizing back to AUTO
circle.primaryAxisSizingMode = "FIXED";    // re-lock to undo the flip
circle.counterAxisSizingMode = "FIXED";    // re-lock
circle.cornerRadius = 20;
```

Both work. Option A reads more cleanly because the intent (auto-layout frame at fixed 40×40) is declared up-front.

**Anti-pattern to recognize:** if your script has the order `resize(w, h)` → `cornerRadius = r` → `layoutMode = "X"` (or any pair where `layoutMode` is the LAST sizing-related setter), you have this bug. Move the `layoutMode` line earlier OR re-lock both sizing modes after it.

**Related:** G16 (the inverse — resize after layoutMode loses FILL/HUG intent), G49 (new auto-layout frames inherit AUTO by default).

### SVG / VECTOR — `svg`, `vector`

**G21. `set_vectorPaths` requires space-separated tokens.** `M16 3C13.4288 3` fails with `Invalid command at M16`. Normalize:

```javascript
const normalized = data.replace(/([MLHVCSQTAZmlhvcsqtaz])/g, ' $1 ').replace(/\s+/g, ' ').trim();
```

**G22. `set_vectorPaths` reliably supports only M, L, Z.** Per Figma forum, **C and Q may fail as the FIRST command** of a path (continuation use is OK). H and V shorthand are unsupported and throw — expand to absolute L commands tracking current point.

**G23. Multiple subpaths in one `data` string render as a connected polygon.** Use separate VECTOR nodes per stroke, or separate objects in the `vectorPaths` array.

**G24. Multi-node icons can show cropping artifacts despite `clipsContent=false`.** Wrap each stroke in its own minimally-sized VECTOR node within a parent frame.

**G25. `figma.createNodeFromSvg(svgString)` handles full SVG including cubic Bezier C curves.** This is the most reliable way to render icons from React component path data. Wrap in try/catch and fall back to a placeholder rectangle if needed.

### Color, paint, fills — `color`, `paint`, `fill`

**G26. Color range is 0–1.** `{r: 1, g: 0, b: 0}` is red. Don't use 0–255.

**G27. Paint shape: `{type: 'SOLID', color: {r,g,b}, opacity: 0.5}`.** Opacity is at the paint level, not in the color object. The color object is `{r,g,b}` only — no `a` field.

**G28. `fills` and `strokes` are read-only arrays.** Clone, modify, reassign:

```javascript
const fills = clone(node.fills);
fills[0].opacity = 0.5;
node.fills = fills;
```

Never mutate in place — `node.fills[0].opacity = 0.5` silently no-ops.

**G29. `setBoundVariableForPaint` returns a NEW paint object.** Capture the result and reassign to the node.

### Variables — `variable`, `scope`

**G30. Always set `variable.scopes` explicitly.** Default `ALL_SCOPES` pollutes every property picker in Figma. Common scopes:

- `["FRAME_FILL", "SHAPE_FILL"]` — background colors
- `["TEXT_FILL"]` — text colors
- `["GAP"]` — spacing
- `["STROKE"]` — borders

**G31. `lineHeight` / `letterSpacing` require `{unit, value}` shape**, not bare numbers. Bare-number assignment is a silent type-mismatch.

### Traversal + query — `traverse`, `query`, `find`

**G32. `node.children` THROWS on non-container types.** RECTANGLE, VECTOR, ELLIPSE, TEXT all throw. Guard:

```javascript
if ('children' in node && Array.isArray(node.children)) { /* ... */ }
```

**G33. Modern: `node.query(selector)` CSS-like search** replaces verbose `findAll` loops:

```javascript
frame.query('TEXT[name=Title]')              // TEXT children named "Title"
figma.currentPage.query('FRAME > TEXT')      // Direct children
figma.currentPage.query('[fills.0.type=SOLID]')  // Dot-path traversal
```

**G34. Modern: `node.set({ ... })` batch property updates:**

```javascript
frame.set({ opacity: 0.5, cornerRadius: 8, name: "Card" })
```

**G35. Modern: `await node.screenshot({ scale: 2 })` inline.** Returns the image without needing a separate `get_screenshot` tool call. Saves a round-trip.

### Promise management — `promise`, `async`, `await`

**G36. Every async call must be `await`ed.** Unawaited promises cause silent failures or races. List of methods that REQUIRE await:

- `figma.loadFontAsync(...)`
- `figma.setCurrentPageAsync(...)`
- `figma.listAvailableFontsAsync(...)`
- `figma.importComponentByKeyAsync(...)`
- `figma.getNodeByIdAsync(...)`
- `node.screenshot(...)`

### Library + plugin data — `library`, `sharedPluginData`

**G37. `setSharedPluginData` namespace must be alphanumeric / `_` / `.`** — hyphens reject. `'ep-ds'` fails; `'epds'` works.

**G38. Library subscriptions are per-file.** Parallel-library files (e.g. a "Custom DS" file separate from the main audit copy) do NOT inherit subscriptions. Add explicitly per file via Figma UI (Assets panel → Libraries — the Plugin API doesn't expose subscribe).

### Platform — `platform`, `windows`

**G39. Windows-native Figma MCP has known connection flakiness** — see [claude-code#5125](https://github.com/anthropics/claude-code/issues/5125). If a `use_figma` call hangs or returns connection errors on Windows, that's likely the issue, not your script.

### Icons — `icon`, `phosphor`, `library-component`

**G40. Never `createNodeFromSvg` for icons that exist as library components.** Re-drawing a Phosphor `Info` / `Eye` / `NotePencil` / `DotsThreeVertical` icon as SVG breaks design-system consistency, won't auto-update when the library changes, and visually drifts from the rest of the page. Canonical approach:

```javascript
// 1. Find any existing instance of the icon in the file
const sampleInst = await figma.getNodeByIdAsync("<nested-instance-id>");
// 2. Get its main component (works for remote library mains)
const main = await sampleInst.getMainComponentAsync();
// 3. Spawn a new instance from the main
const inst = main.createInstance();
inst.resize(target, target);
parent.insertChild(idx, inst);
```

**G41. `importComponentByKeyAsync(key)` can throw "not found" for keys captured from existing instances** even when the subscription is active — the key resolution path differs from cross-file imports. The `getMainComponentAsync()` → `createInstance()` route via a same-file sample is the reliable workaround. Captured 2026-05-18 swapping v15 Transactions action-column icons: `Info` (key `b53ce0a8…`) threw on direct import but the same key resolved fine via the sample-instance path.

**G42. Phosphor icon instances default to a token-bound fill** (typically `color/text-primary` → black-100). To recolor, traverse to the inner VECTOR child and override `fills` directly at the instance level — this breaks only that instance's variable binding, not the library component's:

```javascript
function paintInner(n, color) {
  if (n.type === "VECTOR" && 'fills' in n) {
    n.fills = [{ type: "SOLID", color }];  // overrides variable binding
  }
  if ('children' in n) for (const c of n.children) paintInner(c, color);
}
paintInner(eyeInst, { r: 0, g: 0x81/255, b: 0x9B/255 });  // primary-aqua
```

**G43. Phosphor library components are usually 32×32 native.** Resize after `createInstance()` to the target slot size (14 for info-row carets, 20 for table-action icons, 24 for button leading icons).

**G44. Canonical icon ≠ library COMPONENT.** Some icons in the AcmeLending audit copy live as plain top-level FRAMEs imported from svgrepo (e.g. Xero brand mark — name `xero-svgrepo-com 1`, id `13261:195594`, 16×16). They register zero hits in INSTANCE-only probes. Extend the search to non-INSTANCE node types before falling back to `createNodeFromSvg`:

```javascript
// Phase 1: scan for INSTANCEs (library components)
// Phase 2: if no hits, scan for FRAME / GROUP / VECTOR with matching name
// Phase 3: only then fall back to createNodeFromSvg

// To clone a bundled-SVG FRAME:
const source = await figma.getNodeByIdAsync(canonicalFrameId);
const copy = source.clone();
parent.insertChild(idx, copy);
copy.resize(target, target);
```

### Mixed inline-format text — `setRangeFontName`, `setRangeFills`, wrap behavior

**G47. Mixed inline-format text must be one TEXT node, not separate children.** When HTML renders `<span class="font-semibold">BOLD</span> regular text…` and wraps across multiple lines, line 2+ flows back to the parent's left edge (HTML inline-text-flow). The naive Figma equivalent — two TEXT children in a HORIZONTAL `layoutWrap=WRAP` frame — does NOT replicate this: when the second TEXT wraps, line 2+ hang-indent under where the second TEXT started (not the parent's left edge). To match HTML inline-text-flow:

```javascript
// ✓ RIGHT — single TEXT node with per-character formatting
const txt = figma.createText();
txt.fontName = { family: "Inter", style: "Regular" };  // default for whole string
txt.fontSize = 14;
txt.characters = "CLICK HERE Click here to confirm that the information…";
parent.appendChild(txt);
txt.textAutoResize = "HEIGHT";
txt.layoutSizingHorizontal = "FILL";  // takes parent's available width

// Override the first 10 characters to Semi Bold
txt.setRangeFontName(0, 10, { family: "Inter", style: "Semi Bold" });
// Also available: setRangeFills, setRangeTextDecoration, setRangeFontSize, etc.
```

```javascript
// ✗ WRONG — two TEXT children in layoutWrap; line 2+ hang-indent under span 2
const wrap = figma.createFrame();
wrap.layoutMode = "HORIZONTAL";
wrap.layoutWrap = "WRAP";
const t1 = figma.createText();  t1.fontName = { family: "Inter", style: "Semi Bold" };  t1.characters = "CLICK HERE ";  wrap.appendChild(t1);
const t2 = figma.createText();  t2.fontName = { family: "Inter", style: "Regular" };    t2.characters = "Click here to confirm…";  wrap.appendChild(t2);
// → "Click here to confirm…" wraps INSIDE t2's column, not back to the wrap's left edge
```

**Sequencing**: append the TEXT to its parent BEFORE setting `layoutSizingHorizontal = "FILL"`. Setting FILL before append leaves the text at width 0 (Figma needs the parent to determine the FILL target).

### Rotation — `rotation`, `setProperties` vs CSS transform

**G48. Figma's `node.rotation` is opposite-sign of CSS's `transform: rotate()`.**
- **Figma:** positive `rotation` = counterclockwise (per [Figma plugin API docs](https://www.figma.com/plugin-docs/api/properties/nodes-rotation/)).
- **CSS:** positive `rotate()` = clockwise (standard 2D screen coords, y-down).

When porting an icon's CSS `-rotate-90` (CCW 90 in CSS = CW 90 in Figma's convention) to a Figma node, set `node.rotation = 90` (positive 90 in Figma = CCW). The signs are MIRRORED.

```javascript
// CSS source: className="-rotate-90" (CCW 90 in CSS = makes left-caret point DOWN)
// Wrong in Figma:
node.rotation = -90;   // CW 90 in Figma → left-caret points UP

// Right in Figma:
node.rotation = 90;    // CCW 90 in Figma → left-caret points DOWN
```

Caught 2026-05-20 building chevron-down indicators on Select fields in v23 + v24 modal-form renders. The chevrons came out pointing UP on first try. Fix-pass: flipped sign.

For directional icons (caret, chevron, arrow, triangle), eyeball-verify after rotation. If the symbol's native SVG orientation isn't obvious, try `rotation = 0` first to see the baseline, then add a quarter-turn at a time.

### Variant properties — `setProperties`, `variantGroupProperties`

**G46. `setProperties` silently fails when the value is not in the variant set.** Setting `instance.setProperties({Type: "Customers"})` on a `Sidebar/Staff users` instance whose Type values are `["Simple","Applications","Loans","Dashbord","Batch files","Default","Reports","Setting","Profile"]` does NOT throw — it just silently no-ops. The instance retains its previous Type value, and `componentProperties` reflects the unchanged state. Captured 2026-05-19 building v19 Customer Personal Details: tried to set `Type=Customers` to match the page context, got no error, but the rendered Figma still showed the previous Type=Loans highlight.

**Defensive check before `setProperties`:**

```javascript
const main = await instance.getMainComponentAsync();
const setNode = main && main.parent && main.parent.type === "COMPONENT_SET" ? main.parent : null;
const allowed = setNode && setNode.variantGroupProperties
  ? setNode.variantGroupProperties[propertyName]?.values
  : null;
if (allowed && !allowed.includes(desiredValue)) {
  return { error: `Variant "${desiredValue}" not in set; available: ${allowed.join(", ")}` };
}
instance.setProperties({ [propertyKey]: desiredValue });
```

`variantGroupProperties` is on the COMPONENT_SET parent, not on the instance itself. Walk: `instance → main component → parent component-set → variantGroupProperties`.

---

## 3. Pre-flight checklist (cut-and-paste into your `use_figma` description)

```
Pre-flight ops in this script:
  [ ] Structure: no IIFE wrap, top-level await + return (G1)
  [ ] Logical ops ≤ 10 (G2); if more, split into chunks
  [ ] Returns { createdNodeIds, mutatedNodeIds, ...state } (G3)
  [ ] create-many → if >20 nodes total, split into multiple calls
  [ ] delete → collect ids first, then delete (don't iterate-and-remove)
  [ ] cross-page → setCurrentPageAsync(target) FIRST (G4-G7)
  [ ] clone → lands on currentPage/first page, NOT source page (G8): appendChild to target page + reset x/y + VERIFY parent page name; check inherited auto-layout (G9); detach returns new node (G11)
  [ ] svg / vector → tokenize path (G21); M/L/Z safe, C/Q risky (G22)
  [ ] icons → look for canonical library component FIRST (G40); if zero INSTANCE hits, also scan FRAME/GROUP/VECTOR by name (G44); only fall back to SVG if all three search phases miss
  [ ] text → load font (G13), set autoResize BEFORE characters (G15)
  [ ] layout → resize BEFORE sizing (G16), layoutSizing AFTER appendChild (G17)
  [ ] color → 0-1 range (G26), opacity at paint level (G27)
  [ ] every async is awaited (G36)
```

---

## 4. Migration notes — what changed 2026-05-18

After reading the canonical SKILL.md, several earlier entries in this file were corrected or downgraded:

| Old entry | Status now | Reason |
|---|---|---|
| "Single-script ~150-node silent abort" | Downgraded to "empirical observation" — the SKILL.md says ~10 logical ops/call. Our 150 threshold was 15× over the safe limit. Likely the 30s MCP transport timeout (G2). |
| "Sentinel rectangle pattern for readback" | Removed as primary pattern — use `return` directly (G3). Sentinels are only a fallback if returns are blocked for some other reason. |
| "Iterate-while-remove breaks the script" | Probably caused by the IIFE wrap, not by the iteration pattern itself. Wrap-related symptom; pattern is safe with proper script structure. |
| "Page `.children.length` reads 0 for non-current pages" | Confirmed — this is per-page lazy loading. Use `setCurrentPageAsync` first (G7). |
| "`txt.resize()` causes wrapping" | Refined per SKILL.md — set `textAutoResize` BEFORE characters; don't call `.resize()` on text nodes directly (G15). |
| "`set_vectorPaths` only M/L/C/Z" | Refined — M/L/Z always safe; C/Q may fail as first command. Use `createNodeFromSvg` for complex paths (G22, G25). |

---

## Changelog

- 2026-05-18 (PM3): added G44 after BA flagged that the canonical Xero icon DOES exist in the file — as a plain FRAME named `xero-svgrepo-com 1`, not a library COMPONENT. Initial probe scoped to INSTANCEs only and missed it. Search protocol now: phase 1 INSTANCE-by-name, phase 2 FRAME/GROUP/VECTOR-by-name, phase 3 SVG fallback only after both miss.
- 2026-05-18 (PM2): added G40-G43 (icon-component reuse) after BA flagged SVG-redrawn icons in v15 Transactions. Captured the `getMainComponentAsync()` → `createInstance()` workaround for when `importComponentByKeyAsync()` rejects keys captured from existing instances. Pre-flight checklist updated.
- 2026-05-18 (PM): wholesale rewrite after reading the canonical [figma/mcp-server-guide SKILL.md](https://github.com/figma/mcp-server-guide/blob/main/skills/figma-use/SKILL.md). Added G1 (no IIFE wrap), G2 (10-ops ceiling), G3 (return-based readback), G4-G7 (page lifecycle), G13-G18 (font + text + layout ordering), G26-G31 (color + paint + variable scopes), G33-G35 (modern query/set/screenshot APIs), G36 (promise management). Reorganized as: §0 required structure first, §1 quick index, §2 by-operation deep-dives, §3 pre-flight checklist, §4 migration notes.
- 2026-05-18 (AM): first extraction from prose entries in `memory/project_ux_audit_acme.md`. Organized by operation keyword. 22 gotchas, sessions 2026-05-13 through 2026-05-18.

---

## 5. More traps — first recorded on NWE (2026-07 to 2026-09)

- **`search_design_system` matches single terms only.** A multi-word query
  (`"input card select badge"`) returns `{}` — which reads as "library is empty" and is
  wrong. Query one term at a time.
- Always pass `includeLibraryKeys` (see §2) — the file subscribes to 8 libraries.
- `get_screenshot` returns a short-lived URL; `curl` it rather than requesting base64.
- Page-level screenshots are cheap and good for orienting; `get_metadata` on a whole page
  returns the full subtree and is expensive.
- **`get_metadata` with no `nodeId` does not list every page.** It missed both `Northwind / Screens` and
  `Northwind / Partners (2.2)`. To enumerate pages reliably, run `figma.root.children` through
  `use_figma` instead — otherwise you will conclude work does not exist when it does.
- **Inline `await node.screenshot()` does not composite translucency.** A modal scrim at
  `opacity: 0.45` renders as if absent, which reads as "the scrim is broken" and invites pointless
  debugging. The node is fine — verify overlays with the `get_screenshot` tool (curl the URL), which
  composites correctly.
- **`node.query('FRAME[name=Two Words]')` silently returns nothing.** The selector's attribute value does not
  survive spaces, so a layer called `Course details card` never matches and `.first()` hands back `null` — which
  surfaces one line later as `cannot read property 'children' of null`, pointing at the wrong statement. Use
  `node.findOne(n => n.name === '…')` for any multi-word layer name; `query` is fine for single-word ones (`tabs`).
- **Cloning a `field` frame into an auto-layout parent collapses it to 1px.** The Company Page's
  `field` frames position their label and input absolutely, so an auto-layout parent hugs them to
  nothing. After appending, set `layoutSizingVertical = 'FIXED'` and `resize()` to the children's
  extent.
- **A text layer renames itself to its own content.** Set `characters` to *"Latest content"* and the layer
  called `Section Title` is now called `Latest content`. So a `findOne(n => n.name === 'Section Title')`
  written before the edit silently returns `null` on the second pass. Match on `characters`, or navigate
  by child index — never re-find a text node by the name it had before you wrote to it.
- **`findOne` does not reach inside a freshly cloned instance.** `section.clone()` then
  `clone.findOne(… 'Section Title')` returns `null` even though the node is plainly there and the
  identical call works on the source. Walk `clone.children` explicitly to reach an instance's text.
- **Setting `.y` on a child of an auto-layout frame is silently ignored.** The mobile Home screen
  (`ScreenContent`) is `layoutMode: VERTICAL`, so block order comes from **child index**, not coordinates.
  A block appended with `appendChild` lands last no matter what `y` you give it — reorder with
  `parent.insertChild(index, node)`. The tell is a script that reports success while the screenshot shows
  the old order, and a read-back where `before` and `after` are identical.
- **Resize the parent BEFORE positioning children, not after.** Growing a frame moves its children
  according to their constraints, so positions set first are thrown away by the resize that follows.
- **`textAutoResize` is a font-gated write like `characters`.** Setting it without loading the node's
  current fonts throws `Cannot write to node with unloaded font "Poppins Regular"` — the same canonical
  recipe applies to it.
- **A child with `layoutSizingVertical = 'FILL'` inside a HUGGING parent collapses to 1px and clips.**
  FILL wins over the parent's hug, so the parent measures the child as nothing and the child then hides
  everything inside it. On the Home post cards this silently erased a post body *and* the image below it,
  while `get_screenshot` showed a half-empty card and every property read looked plausible
  (`bodyW=344`, `imgVisible=true`). The tell is a frame reporting `[344x1]` with `sz=FILL/FILL` where its
  siblings report `sz=FILL/HUG`. Fix: `child.layoutSizingVertical = 'HUG'`. Setting the parent's
  `primaryAxisSizingMode = 'AUTO'` does **not** override it.
- **`layoutSizing*` always beats `primaryAxisSizingMode` — the two are not interchangeable.** Setting
  `primaryAxisSizingMode = 'AUTO'` on a node whose `layoutSizingVertical` is `FIXED` does nothing at all:
  the call succeeds, reports success, and the height never changes. Set `layoutSizingVertical = 'HUG'`
  instead. And to make a card hug you must clear FILL **all the way down** — a card whose inner container
  still fills can never hug, because its height stays indeterminate.
- **`textAlignHorizontal` is font-gated too.** Same error as `characters` and `textAutoResize`
  (`Cannot write to node with unloaded font "Poppins SemiBold"`). Load the node's own fonts first.
- **The DS `Buttons` set is `Accent` / `Secondary` / `Ghost-Link`, and `Secondary` has a WHITE label** —
  it was drawn for the dark event hero. Dropped on a light card it renders as an empty outline. Override
  its text fill and stroke to brand violet on light surfaces.
- **A DS button at half-card width overflows its own label.** `Buttons` carries 24px side padding and
  `primaryAxisAlignItems = 'MIN'`, so at 116px wide an 87px label ("View Details") has 68px to sit in and
  spills left. Centre it and drop the padding to ~12px.
- **Dump `layoutSizing*` when a Figma layout misbehaves.** Sizes and visibility alone will not show you
  this class of bug — print `layoutSizingHorizontal/Vertical`, `primaryAxisSizingMode`,
  `counterAxisSizingMode`, `primaryAxisAlignItems` and `clipsContent` next to a known-good sibling and the
  difference is obvious in one read.
- **A SECTION's children use coordinates RELATIVE to the section — frames on the page do not.** So the
  familiar `child.y = parent.y + 120` is wrong inside a section: it adds the section's own offset a second
  time. A panel meant for a section at `y=3167` landed at `y=6454`, i.e. thousands of pixels below its own
  box, and the section rendered **completely empty** while every child screenshot looked perfect and every
  position read back as expected. Set `child.x/​y` relative (`80`, `120`). ⚠️ The tell that this has happened:
  `node.absoluteBoundingBox.y !== node.y` for a section child. Compare `absoluteBoundingBox` against `x`/`y`
  whenever a container looks empty — a bounds calculation written as `child.y - section.y` gives the SAME
  plausible answer either way and will not catch it.
- **⛔ NEVER RESIZE AN AVATAR INSTANCE — swap the variant.** The DS `Avatar` set (`Size=sm` 32 · `Size=md` 40
  · `Size=lg` 56) is a **remote library component and read-only**, and its inner masked circle carries
  `MIN/MIN` constraints. Resize the instance and the circle stays at its original size, so the photo spills
  outside the frame — a square-ish portrait next to round ones. The instance itself reports the size you
  asked for, so nothing looks wrong in a read; you only see it on the canvas. `constraints` cannot be fixed
  on the master (`Cannot write to internal and read-only node`). **Audit with:** compare every
  `INSTANCE` named `*avatar*` against `getMainComponentAsync().width` — any mismatch is this bug.
- **`ConversationList.tsx` renders the inbox avatar at `size-11` (44px), which the DS set has no variant
  for.** A local `Avatar / Size=44 (NWE addition)` exists for it; use that rather than resizing a `md`.
- **A HUG frame can report every sizing mode correctly and STILL hold a stale height.** On the mobile post
  cards the text container read back `sz=FILL/HUG`, `pri=AUTO`, gap 12, padding 16/16, children summing to
  **340** — and its height was **328**. Figma then laid the children out against the stale 328, putting the
  action row at `y=292` instead of `y=304`, i.e. **on top of the post image**. Re-setting HUG does not
  dislodge it. Fix: compute the height yourself
  (`padTop + padBottom + gap*(n-1) + Σ visible child heights`), set the parent `FIXED` to that, and set the
  inner container back to `FILL` so `SPACE_BETWEEN` still pins the footer. ⚠️ **Only count VISIBLE children** —
  a hidden image would otherwise add 160px of dead space. Same class of bug clipped the `View` button on the
  content carousel cards, where a `FILL` body inside a too-short fixed card lost 18px off the bottom.
- **Property reads immediately after a layout mutation are stale.** Heights returned in the same script
  that changed them came back as the pre-change values (three cards all reporting `320` after one had lost
  its image). Re-read in a fresh `use_figma` call, or verify with `get_screenshot`.
