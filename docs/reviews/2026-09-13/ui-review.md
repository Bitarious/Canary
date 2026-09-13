# Browser review

Reviewed GitHub main `6155189` in a local isolated checkout. The 3D app used only its generated demonstration fleet. The auxiliary Backblaze preview used the existing development dataset. The hardware benchmark and telemetry-write endpoints were not used.

## Blocker

**A trained-model demonstration is not connected.** At 1440 by 900, open Site A, Rack 06, Server 609, Analyze, then Disk 3. The drawer shows 85% seven-day failure risk, a two-to-six-day window, and high confidence. Its footer identifies `driftops-baseline-v0`. These values come from formulas and templates in `driftops3d/driftops/model.py`, not the trained checkpoint.

This blocks the claim that the current interface demonstrates trained inference. It does not block using the app as an illustrative workflow. Add a distinct output-origin label, connect actual saved model outputs, and leave unsupported probability fields unavailable.

Evidence: [component screenshot](screenshots/component-desktop.png). Source: `model.py:495` defines the hazard formula. `model.py:735` assigns confidence from signal and history counts. `web/js/panel.js:123` presents the resulting value as failure risk.

## High

**Historical replay and copilot answers disagree.** At 1440 by 900, select the Server 609 drift row, choose `−30d`, then ask `Why?`. The interface shows 29 days ago, no drifting devices, and Server 609 at 89. The new answer still describes today's Disk 3 at 24, with 92 reallocated sectors and a two-to-six-day failure window.

The expected answer must use the selected cutoff or state that no historical answer is available. Pass the cutoff through the copilot request and resolve the corresponding observations. Existing replies also need their own visible dates.

Evidence: [replay screenshot](screenshots/twin-past-copilot.png). Source: `web/js/main.js:241` changes the rendered frame. `driftops/copilot.py:64` reads current fleet summaries without a cutoff.

**The main action is clipped on a phone.** At 390 by 844, the header's Analyze button starts at x=371 and extends to x=477. Most of the button lies outside the 390-pixel viewport. The page cannot scroll horizontally to expose it.

Keep the main action visible. Move the hardware benchmark into secondary controls and collapse navigation where necessary.

Evidence: [mobile twin](screenshots/twin-390.png) and [mobile component](screenshots/component-390.png). DOM bounds confirm the clipping.

## Medium

**3D labels overlap the mobile evidence drawer.** At 390 by 844, open Disk 3. The `Disk 2 100` scene label crosses the drawer title. Several scene labels also collide at the edges. The open evidence drawer should remain readable above scene annotations.

Evidence: [mobile component](screenshots/component-390.png). Adjust scene-label stacking or hide labels behind the drawer. The underlying camera motion was not diagnosed in this review.

**The presentation's technical status is obsolete.** Slide 10 still describes the 3,000-drive pilot and omits trained LoRA. Slide 13 lists first GPU training and held-out evaluation as future work. The completed artifacts now cover full-history HDD training and thirteen passing component categories. Update these slides from the measured results, while retaining the limits of weak-label evaluation.

Evidence: [architecture slide](screenshots/deck-slide-10.png) and [status slide](screenshots/deck-slide-13.png).

**The default path takes several steps before evidence appears.** From the site view, the tested path selected a drifting device, opened its 3D view, clicked Analyze, then selected the component. A saved dataset result should open with the component. Retain Analyze for an explicit fresh computation.

## Polish

The presentation's serif headings, restrained colors, and spacing work at desktop size. Keep this visual language while reducing the content. The sources slide is dense and belongs in an appendix.

The Backblaze preview and deck each request a missing favicon. This produces a 404 without interrupting the content.

The 3D app produced four WebGL `ReadPixels` performance warnings during desktop inspection. No JavaScript exception or failed essential asset request occurred in the normal tested journey. This is not a measured frame-rate benchmark.

## Verification and limits

Observed successful paths: site and rack navigation, server cutaway, component analysis, laptop navigation and analysis, replay controls, fleet search, empty search state, incidents, and recovery from an unknown device through the Twin link. An unknown device showed a readable error and retained navigation. Its deliberate API 404 is expected.

The 3D twin and open component drawer were inspected at 390 by 844, 768 by 1024, 1440 by 900, and 2560 by 1440. The desktop view fits the rack scene, sidebar, and copilot. The narrower layouts retain a scrollable drawer, but have the issues above. The tablet sidebar is collapsed, so touch selection and keyboard alternatives warrant further accessibility testing.

The Backblaze preview displayed real raw windows and changed them through Next. A negative window index returned HTTP 400 with an explicit message. Its source and rule-description labels were visible.

All sixteen deck slides were inspected in the browser. A bounding-box check found no heading or paragraph outside the slide. Final screenshots waited for transitions to finish. Desktop body text and footnotes still need a room-distance rehearsal on the actual projector.

Three.js modules and fonts loaded successfully from jsDelivr and Google during this review. The app therefore currently depends on those external requests. Offline venue behavior was not tested. Bundle or cache those assets before an offline demonstration and verify with network access disabled.

This was a focused browser and source review, not a full accessibility audit. No screen-reader, comprehensive keyboard, telemetry ingestion, hardware benchmark, production deployment, or cold model inference test ran. The repository's separate Chrome navigation script was inspected but not executed. Browser interactions provided the runtime evidence reported here. Existing 93-test training verification predates this review and does not prove UI integration.

Screenshots are in `screenshots/`. The browser tool first required its allowed workspace output directory. Review screenshots were then moved to the prescribed artifact directory.
