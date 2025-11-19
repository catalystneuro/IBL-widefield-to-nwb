# Notes concerning the widefield2025 conversion

# Converting processed IBL widefield data to NWB format

This section describes the expected input file structure for a processed IBL widefield session and how those data are
written into NWB by the widefield2025 pipeline in this repository.

## Expected input folder structure
The converter expects the following files to exist when running the conversion:

- `imaging.imagingLightSource.npy`
  - 1-D array of length equal to the total number of acquired frames across both channels.
  - Each entry contains the `channel_id` used for that frame. In current IBL data, channel_id=2 corresponds to the 470 nm (Blue) functional/calcium channel, and channel_id=1 corresponds to the 405 nm (Violet) isosbestic channel.
- `imaging.times.npy`
  - 1-D array of timestamps (in seconds) aligned to the frames in the same order as imagingLightSource. The converter filters these timestamps by channel to get per-channel timestamps.
- `imagingLightSource.properties.htsv`
  - Tabular file (read as CSV) containing properties for each `channel_id`. At minimum must include columns: `channel_id`, `color`, `wavelength`. Wavelength 470 implies calcium; any other (e.g., 405) is treated as isosbestic.
- `widefieldChannels.frameAverage.npy`
  - Array of per-channel mean images.
- `widefieldSVT.haemoCorrected.npy`
  - 2-D array with shape (num_rois, total_num_frames) containing haemodynamically corrected signals. Used only for the 470 nm functional channel and exported as dF/F for that channel.
- `widefieldSVT.uncorrected.npy`
  - 2-D array with shape (num_rois, total_num_frames) containing uncorrected fluorescence signals. Used for both channels as the raw ROI traces.
- `widefieldU.images.npy`
  - ROI image masks for the segmentation (e.g., shape (num_rois, height, width)). These masks are added to the `PlaneSegmentation` tables in NWB.

Notes:
- Shapes are expected as produced by the IBL processing pipeline. The extractor transposes ROI-by-time arrays to time-by-ROI when writing to NWB.
- If more than one channel is present and no channel_id is provided, the converter will warn and default to the first detected channel.

## How data are written to NWB
The conversion uses `WidefieldProcessedNWBConverter`. For each channel converted, the following NWB structures are created and populated:

1) Ophys/ImagingPlane
- Name: `imaging_plane_calcium` for 470 nm or `imaging_plane_isosbestic` for 405 nm.
- `excitation_lambda` set from `imagingLightSource.properties.wavelength`.
- `emission_lambda` set from  metadata YAML (`metadata/widefield_ophys_metadata.yaml`).

2) Ophys/PlaneSegmentation
- Name: `plane_segmentation_calcium` for 470 nm or `plane_segmentation_isosbestic` for 405 nm.
- Descriptions include the channel color.
- The ImagingPlane reference is linked to the corresponding ImagingPlane created above.

3) Ophys/Fluorescence (ROIResponseSeries for raw/unprocessed fluorescence)
- For each channel, a ROIResponseSeries named:
  - `roi_response_series` for 470 nm
  - `roi_response_series_isosbestic` for 405 nm
- The uncorrected array (widefieldSVT.uncorrected...) is filtered to the frames that belong to the channel (using imaging.imagingLightSource), then transposed to time x ROI and written with the per-channel timestamps from imaging.times.

4) Ophys/DfOverF (ROIResponseSeries for dF/F)
- Only for the 470 nm functional channel, a ROIResponseSeries named `roi_response_series` is created under DfOverF, using the haemodynamically corrected signals from widefieldSVT.haemoCorrected..., filtered to frames for that channel and transposed to time x ROI.

5) Ophys/SegmentationImages
- For each channel, the following images are written under the PlaneSegmentation key for that channel:
  - `mean_calcium` or `mean_isosbestic` from widefieldChannels.frameAverage
  - image masks from widefieldU.images... are written as binary/float masks per ROI.
