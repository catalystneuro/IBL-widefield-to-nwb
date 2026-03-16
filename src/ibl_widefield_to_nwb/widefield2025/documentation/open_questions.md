# Open Questions for IBL

These questions arose during the conversion implementation and require IBL input before the
dandiset can be considered finalized.

---

## Q1 — DAQ device metadata

**Where:** `_metadata/widefield_DAQ_metadata.yaml` → NWB `Device` object

**Status: Resolved.** Hardware confirmed; Device metadata updated.

**Confirmed:**
- **Device:** National Instruments USB-6356 (simultaneous-sampling multifunction DAQ,
  8 AI channels, 16-bit, 1.25 MS/s max — operated at 30,000 Hz for IBL widefield sessions)
- **Camera control software:** [labcams](https://github.com/jcouto/labcams)

The `Device` YAML can now be filled in as:

```yaml
WidefieldDAQBoard:
  name: WidefieldDAQBoard
  description: >-
    National Instruments USB-6356 multifunction DAQ device used to record widefield camera frame
    triggers and behavioral synchronization signals. Camera acquisition managed by
    labcams.
  manufacturer: "National Instruments"
```

---

## Q2 — Analog `starting_time` for DAQ channels

**Where:** `IblWidefieldDAQInterface._add_analog_channels()` → `TimeSeries.starting_time`

**Status: Resolved.** Per-device `starting_time` is now computed as follows:

1. **Devices with both analog and digital wiring** (e.g., `bpod` wired to both `AI0` and
   `P0.x`): The timestamp of the first event on the device's digital port (from
   `_spikeglx_sync.times.npy`) is used as `starting_time` for the analog `TimeSeries`.
   This anchors the continuous analog trace to the same hardware clock reference used by
   the corresponding digital events.
2. **Devices with analog wiring only**: The timestamp of the first event on the SpikeGLX
   sync channel (from `_spikeglx_sync.times.npy`) is used as a fallback `starting_time`.
3. **No sync channel available**: Falls back to `starting_time=0.0`.

This approach is correct because both the analog `.cbin` recording and the pre-extracted
`_spikeglx_sync.times.npy` share the same DAQ hardware clock, and SpikeGLX always starts
the clock at t=0 when recording begins.

---

## Q3 — Anatomical landmarks: `AnatomicalCoordinatesImage` in source image space

**Where:** `IblWidefieldLandmarksInterface`

**Status: Resolved.** The landmarks interface is fully implemented in both the raw and
processed pipelines. It is included conditionally whenever `widefieldLandmarks.dorsalCortex.json`
is available for a session. The interface writes:

- Named landmark pixel coordinates (`Landmarks` table)
- Affine transform to Allen CCFv3 (`AffineTransformation`, `AtlasRegistration`)
- Atlas coordinates for each landmark in IBL bregma space and CCFv3 space
  (`AnatomicalCoordinatesTable` objects)
- Per-pixel physical coordinates in IBL bregma space for every pixel of the registered image
  (`AnatomicalCoordinatesImageIBLBregma` — x=ML, y=AP, z=DV, units µm)
- Per-pixel physical coordinates in Allen CCFv3 space for every pixel of the registered image
  (`AnatomicalCoordinatesImageCCFv3` — x=AP, y=DV, z=ML, units µm, PIR orientation)
- Sparse pixel-level Allen brain region masks for the registered image
  (`RegisteredImageBrainRegionMasksIBLBregma`) and the source (camera) image
  (`SourceImageBrainRegionMasksIBLBregma`), both stored under `Localization`

All objects are stored under `nwbfile.lab_meta_data["localization"]` (type `Localization`) and
`nwbfile.lab_meta_data["atlas_registration"]` (type `AtlasRegistration`).
See `processed_nwb.md` and `raw_nwb.md` Section 2/5 for the full NWB output tables.

---

## Q4 — GCaMP indicator and viral vector

**Where:** `_metadata/widefield_ophys_metadata.yaml` → `ImagingPlane.indicator`

**Current value:** `GCaMP6f` (for both the calcium and isosbestic imaging planes)

**Question:** Is `GCaMP6f` correct for all widefield subjects in the target dandiset, or does
the genotype or viral vector vary across subjects (e.g., GCaMP7f, jGCaMP8, transgenic vs.
viral expression)?

If it varies by subject, the indicator should be read from Alyx subject metadata rather than
hard-coded in the YAML.

**Secondary issue:** The isosbestic plane (`ImagingPlaneIsosbestic`) currently also lists
`indicator: GCaMP6f`. This is technically correct (same indicator, different excitation
wavelength) but may confuse downstream tools that parse this field to distinguish signal from
control channels. An alternative is `indicator: "GCaMP6f (isosbestic control)"` or simply
`"isosbestic control"`.

---

## Q5 — Frame trigger count off by one relative to imaging frame count

**Where:** `EventsFrameTrigger` (NWB acquisition) vs. `OnePhotonSeriesCalcium` +
`OnePhotonSeriesIsosbestic` (NWB acquisition)

**Session:** `81f90b18-e61c-4d32-bbce-3e0c5f33f06c` (`sub-FD-28`, DAQ session,
`raw_sync_data/` collection)

**Observed counts (directly from ONE source files — not from NWB):**

```python
one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international")
eid = "81f90b18-e61c-4d32-bbce-3e0c5f33f06c"

sync_times    = one.load_dataset(eid, "_spikeglx_sync.times",      collection="raw_sync_data")
sync_channels = one.load_dataset(eid, "_spikeglx_sync.channels",   collection="raw_sync_data")
sync_pol      = one.load_dataset(eid, "_spikeglx_sync.polarities", collection="raw_sync_data")

frame_trigger_channel = 3  # P0.3 = frame_trigger in wiring.json
rising  = (sync_channels == frame_trigger_channel) & (sync_pol ==  1)
falling = (sync_channels == frame_trigger_channel) & (sync_pol == -1)
# → rising.sum()  = 249773
# → falling.sum() = 249773

all_times    = one.load_dataset(eid, "imaging.times",              collection="alf/widefield")
light_source = one.load_dataset(eid, "imaging.imagingLightSource", collection="alf/widefield")
# → len(all_times)    = 249772
# → len(light_source) = 249773   ← one longer than all_times
```

| ONE source file | Length |
|---|---|
| `_spikeglx_sync.times.npy` — frame_trigger rising edges | 249,773 |
| `imaging.imagingLightSource.npy` | 249,773 |
| `imaging.times.npy` | **249,772** ← one shorter |
| 470 nm frames (`channel_id=2`) after min-length truncation | 124,886 |
| 405 nm frames (`channel_id=1`) after min-length truncation | 124,886 |

**How to reproduce from the NWB file:**

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("sub-FD-28_ses-81f90b18-..._desc-raw_behavior+ophys.nwb", "r") as io:
    nwb = io.read()
    trig = nwb.acquisition["EventsFrameTrigger"]
    frame_on = trig.timestamps[trig.data[:] == 1]
    n_ca  = len(nwb.acquisition["OnePhotonSeriesCalcium"].timestamps[:])
    n_iso = len(nwb.acquisition["OnePhotonSeriesIsosbestic"].timestamps[:])
    print(len(frame_on), n_ca + n_iso)  # 249773  249772
```

**Key finding — the discrepancy is already in ONE:**

`imaging.imagingLightSource.npy` (249,773 entries) is one element **longer** than
`imaging.times.npy` (249,772 entries). The IBL sync pipeline assigned a wavelength index
to all 249,773 trigger pulses but produced a synchronized timestamp for only 249,772 of
them. The production code in `WidefieldImagingInterface.get_aligned_timestamps()` already handles
this silently by truncating to `min(len(all_times), len(light_sources))`.

**Our interpretation:**

The last trigger pulse has a wavelength assignment (in `imagingLightSource.npy`) but no
synchronized timestamp (absent from `imaging.times.npy`). This suggests the final frame was
captured after the reliable portion of the sync window ended — either the NIDQ recording
stopped just before the last pulse could be aligned, or the sync pipeline excluded the last
sample as an outlier. The NWB file faithfully reflects the 249,772 timestamps from
`imaging.times.npy`; the +1 trigger pulse count in `EventsFrameTrigger` comes from the
unfiltered `_spikeglx_sync` source.

The consistency check tolerates ±1 (`abs(trigger_count - total_frames) <= 1`).

**Question for IBL:** Is `len(imaging.imagingLightSource.npy) > len(imaging.times.npy)` by
exactly 1 expected across all widefield sessions, or is this session-specific? Specifically:

1. Does the sync pipeline always produce one fewer aligned timestamp than trigger pulses, or
   only when the recording ends mid-cycle?
2. Should the consistency check enforce `trigger_count == len(imaging.imagingLightSource)` as
   the stricter invariant, tolerating the `imaging.times` shortfall as known pipeline behavior?
3. Is the trailing unaligned frame (with wavelength index but no timestamp) intentionally
   excluded from the NWB, or should it be included with an interpolated timestamp?
