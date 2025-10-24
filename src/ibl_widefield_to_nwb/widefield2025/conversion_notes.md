# Notes concerning the widefield2025 conversion

# Converting raw IBL widefield data to NWB format

This section describes the expected input file structure for a raw IBL widefield session and how those data are
written into NWB by the widefield2025 pipeline in this repository.

## Expected input folder structure
The converter expects exactly one of each of the following files in that folder:

- `imaging.frames.mov`
  - The raw video file containing all acquired frames, interleaving channels frame-by-frame (e.g., 470 nm and 405 nm alternating).
  - Frames are read on demand and converted to grayscale before writing to NWB.
- `widefieldChannels.wiring.htsv`
  - Tab-separated values file containing properties for each illumination channel.
  - Must include a column named `LED` (channel identifier) and should include `wavelength` (in nm) and `color`.
  - The wavelength determines the channel suffix used in NWB metadata: 470 -> calcium (functional), 405 -> isosbestic (control).
- `widefieldEvents.raw.camlog`
  - Text log with one line per acquired frame that encodes the `LED` used, `frame_id`, and `timestamp`.
  - Lines of interest follow the pattern: `#LED:{channel_id},{frame_id},{timestamp}`.
  - These entries are used to filter frames and timestamps by channel.

## How data are written to NWB
The conversion uses `WidefieldRawNWBConverter`. For each channel converted, the following NWB structures are created and populated:

1) Ophys/ImagingPlane
- Name: `imaging_plane_calcium` for 470 nm or `imaging_plane_isosbestic` for 405 nm.
- `excitation_lambda` is set from the .htsv properties for the selected LED (wavelength, in nm).
- `imaging_rate` is set from the per-channel sampling frequency (half of camera FPS due to interleaving).
- Device and optical channel metadata are taken from `metadata/widefield_ophys_metadata.yaml` and updated by the interface to match the channel.

2) Ophys/OnePhotonSeries
- Name: `one_photon_series_calcium` for 470 nm or `one_photon_series_isosbestic` for 405 nm.
- `imaging_plane` is linked to the corresponding ImagingPlane above.
- unit is set to "px".
- Data shape written is (time, width, height); frames are converted to grayscale from the source RGB using OpenCV during read.
- Native timestamps originate from the .camlog entries for the selected channel.

Array shapes and dtype
- get_series returns an array shaped (time, height, width).
- The dtype matches the underlying video frame dtype reported by the reader (`uint8`).
- Frames are converted to grayscale via OpenCV (COLOR_RGB2GRAY) prior to writing.
