# Notes concerning the widefield2025 conversion

## Contents

- [Converting raw IBL widefield data to NWB format](#converting-raw-ibl-widefield-data-to-nwb-format)
  - [Expected input folder structure (raw)](#raw-expected-input)
  - [How data are written to NWB (raw)](#raw-how-data-written)
  - [Array shapes and dtype](#array-shapes-and-dtype)
  - [Example metadata (raw)](#example-metadata-raw)
- [NIDQ](#nidq)
  - [Expected input folder structure (NIDQ)](#nidq-expected-input)
  - [How data are written to NWB (NIDQ)](#nidq-how-data-written)
- [Converting processed IBL widefield data to NWB format](#converting-processed-ibl-widefield-data-to-nwb-format)
  - [Expected input folder structure (processed)](#processed-expected-input)
  - [How data are written to NWB (processed)](#processed-how-data-written)
  - [Example metadata (processed)](#example-metadata-processed)
- [Widefield landmarks and alignment to Allen CCF](#widefield-landmarks-and-alignment-to-allen-ccf)
  - [Expected input (landmarks)](#landmarks-expected-input)
  - [How landmarks are written to NWB](#landmarks-how-data-written)

<a name="raw-expected-input"></a>
## Converting raw IBL widefield data to NWB format

<a name="raw-expected-input"></a>
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

<a name="raw-how-data-written"></a>
## How data are written to NWB
The conversion uses `WidefieldRawNWBConverter`. For each channel converted, the following NWB structures are created and populated:

1) Ophys/ImagingPlane
- Name: `ImagingPlaneCalcium` for 470 nm or `ImagingPlaneIsosbestic` for 405 nm.
- `excitation_lambda` is set from the .htsv properties for the selected LED (wavelength, in nm).
- `imaging_rate` is set from the per-channel sampling frequency (half of camera FPS due to interleaving).
- Device and optical channel metadata are taken from `_metadata/widefield_ophys_metadata.yaml` and updated by the interface to match the excitation wavelength.

2) Ophys/OnePhotonSeries
- Name: `OnePhotonSeriesCalcium` for 470 nm or `OnePhotonSeriesIsosbestic` for 405 nm.
- `imaging_plane` is linked to the corresponding ImagingPlane above.
- Data shape written is (time, height, width); frames are converted to grayscale from the source RGB using OpenCV during read.
- Native timestamps originate from the .camlog entries for the selected channel.
- Aligned timestamps are taken from the processed data (`imaging.times.npy` filtered by the excitation wavelength).

### Array shapes and dtype
- get_series returns an array shaped (time, height, width).
- The dtype matches the underlying video frame dtype reported by the reader (`uint8`).
- Frames are converted to grayscale via OpenCV (COLOR_RGB2GRAY) prior to writing.

<a name="example-metadata-raw"></a>
Example metadata:

```yaml
Ophys:
  Device:
    - name: WidefieldMicroscope
      description: The widefield microscope used to acquire simultaneous dual-wavelength imaging (blue/violet) at ~30 Hz.
  ImagingPlane:
    - name: ImagingPlaneCalcium
      description: The imaging plane for calcium imaging from Blue light excitation.
      excitation_lambda: 470.0  # in nm
      indicator: GCaMP6f # Maybe this was only for Mesoscope and not for Widefield
      optical_channel:
        - name: OpticalChannel
          emission_lambda: 510.0  # in nm (peak emission wavelength)
          description: GCaMP Ca2+ bound emission (calcium signal). (Thorlabs, cat. no. M470L4)
      device: WidefieldMicroscope
    - name: ImagingPlaneIsosbestic
      description: The imaging plane for calcium imaging from Violet light excitation.
      excitation_lambda: 405.0 # in nm
      indicator: GCaMP6f
      optical_channel:
        - name: OpticalChannel
          emission_lambda: 510.0  # in nm (peak emission wavelength)
          description:  GCaMP Ca2+ independent emission (isosbestic signal). (Thorlabs, cat. no. M405L4)
      device: WidefieldMicroscope
  OnePhotonSeries:
    - name: OnePhotonSeriesCalcium
      description: Widefield raw imaging under blue excitation at 470 nm (GCaMP signal).
      imaging_plane: ImagingPlaneCalcium
    - name: OnePhotonSeriesIsosbestic
      description: Widefield raw imaging under violet excitation at 405 nm (isosbestic control).
      imaging_plane: ImagingPlaneIsosbestic
```

<a name="nidq"></a>
# NIDQ

<a name="nidq-expected-input"></a>
## Expected input folder structure
The `SpikeGLXNIDQInterface` expects exactly one of each of the following files in that folder:

```
raw_ephys_data/
├── _spikeglx_ephysData_g0_t0.nidq.cbin
├── _spikeglx_ephysData_g0_t0.nidq.ch
├── _spikeglx_ephysData_g0_t0.nidq.meta
```

## How data are written to NWB

The continuous **analog** channels (e.g. Bpod analog outputs) are written as `TimeSeries` and added to `nwbfile.acquisition`.
The discrete **digital** channels (TTL events) are added as `LabeledEvents` using the `ndx-events` extension, and are
added to `nwbfile.acquisition`.

The metadata for the digital and analog channels (name, description etc.) is taken from `metadata/widefield_nidq_metadata.yaml`.

The wiring file `_spikeglx_ephysData_g0_t0.nidq.wiring.json` is used to determine which analog channels are added to the NWB file.
An example wiring file is shown below:

```json
{
    "SYSTEM": "3B",
    "SYNC_WIRING_DIGITAL": {
        "P0.0": "left_camera",
        "P0.1": "right_camera",
        "P0.2": "body_camera",
        "P0.3": "imec_sync",
        "P0.4": "frame2ttl",
        "P0.5": "rotary_encoder_0",
        "P0.6": "rotary_encoder_1",
        "P0.7": "audio"
    },
    "SYNC_WIRING_ANALOG": {
        "AI0": "bpod"
    }
}
```

In this example, only the analog channel `AI0` (named "bpod") will be added to the NWB file as a `TimeSeries`.

<a name="processed-expected-input"></a>
# Converting processed IBL widefield data to NWB format

<a name="processed-expected-input"></a>
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

<a name="processed-how-data-written"></a>
## How data are written to NWB
The conversion uses `WidefieldProcessedNWBConverter`. For each channel converted, the following NWB structures are created and populated:

1) Ophys/ImagingPlane
- Name: `ImagingPlaneCalcium` for 470 nm or `ImagingPlaneIsosbestic` for 405 nm.
- `excitation_lambda` set from `imagingLightSource.properties.wavelength`.
- `emission_lambda` set from metadata YAML (`_metadata/widefield_ophys_metadata.yaml`).

2) Ophys/SVDSpatialComponents
- Name: `SVDTemporalComponentsCalcium` for 470 nm or `SVDTemporalComponentsIsosbestic` for 405 nm.
- The spatial components from `widefieldU.images.npy` are written as height x width arrays for each spatial component and added to `SVDTemporalComponentsCalcium.image_mask` and `SVDTemporalComponentsIsosbestic.image_mask`.
- The `imaging_plane` reference is linked to the corresponding ImagingPlane created above.

3) Ophys/SVDTemporalComponents
Denoised SVD Temporal Components:
- Name: `DenoisedSVDTemporalComponentsCalcium` for 470 nm or `DenoisedSVDTemporalComponentsIsosbestic` for 405 nm.
- The uncorrected SVD temporal components (`widefieldSVT.uncorrected...`) is filtered to the frames that belong to the channel (using imaging.imagingLightSource), then transposed to time x ROI and written with the per-channel timestamps from imaging.times.
Haemodynamically Corrected SVD Temporal Components:
- Name: `HaemoCorrectedSVDTemporalComponentsCalcium` for 470 nm
- Only available for the 470 nm functional channel, extracted from `widefieldSVT.haemoCorrected...`, and transposed to time x ROI.

4) Ophys/SummaryImages
- Name: `MeanImage` for 470 nm or `MeanImageIsosbestic` for 405 nm.
- The summary images from `widefieldChannels.frameAverage` are written as height x width arrays.

<a name="example-metadata-processed"></a>
## Example metadata (processed)

```yaml
Ophys:
  Device:
    - name: WidefieldMicroscope
      description: The widefield microscope used to acquire simultaneous dual-wavelength imaging (blue/violet) at ~30 Hz.
  ImagingPlane:
    - name: ImagingPlaneCalcium
      description: The imaging plane for calcium imaging from Blue light excitation.
      excitation_lambda: 470.0  # in nm
      indicator: GCaMP6f # Maybe this was only for Mesoscope and not for Widefield
      optical_channel:
        - name: OpticalChannel
          emission_lambda: 510.0  # in nm (peak emission wavelength)
          description: GCaMP Ca2+ bound emission (calcium signal). (Thorlabs, cat. no. M470L4)
      device: WidefieldMicroscope
    - name: ImagingPlaneIsosbestic
      description: The imaging plane for calcium imaging from Violet light excitation.
      excitation_lambda: 405.0 # in nm
      indicator: GCaMP6f
      optical_channel:
        - name: OpticalChannel
          emission_lambda: 510.0  # in nm (peak emission wavelength)
          description:  GCaMP Ca2+ independent emission (isosbestic signal). (Thorlabs, cat. no. M405L4)
      device: WidefieldMicroscope
  ImageSegmentation:
    name: SVDSpatialComponents
    plane_segmentations:
      - name: SVDTemporalComponentsCalcium
        description: Spatial components for widefield calcium imaging.
        imaging_plane: ImagingPlaneCalcium
      - name: SVDTemporalComponentsIsosbestic
        description: Spatial components for widefield calcium imaging.
        imaging_plane: ImagingPlaneIsosbestic
  Fluorescence:
    name: SVDTemporalComponents
    SVDTemporalComponentsCalcium:
      raw:
        name: DenoisedSVDTemporalComponentsCalcium
        description: SVD temporal components (denoised/decomposed) of widefield calcium imaging from Blue light (470 nm) excitation.
        unit: n.a.
      haemocorrected:
        name: HaemoCorrectedSVDTemporalComponentsCalcium
        description: Haemodynamic corrected SVD temporal components of widefield calcium imaging from Blue light (470 nm) excitation.
        unit: n.a.
    SVDTemporalComponentsIsosbestic:
      raw:
        name: DenoisedSVDTemporalComponentsIsosbestic
        description: SVD temporal components (denoised/decomposed) of widefield calcium imaging from Violet light (405 nm) excitation.
        unit: n.a.
  SegmentationImages:
    name: SummaryImages
    description: Summary images for widefield calcium imaging.
    SVDTemporalComponentsCalcium:
      mean:
        name: MeanImage
        description: The mean image under Blue (470 nm) excitation across the imaging session.
    SVDTemporalComponentsIsosbestic:
      mean:
        name: MeanImageIsosbestic
        description: The mean image under Violet (405 nm) excitation across the imaging session.
```

<a name="widefield-landmarks-and-alignment-to-allen-ccf"></a>
# Widefield landmarks and alignment to Allen CCF

The `widefieldLandmarks.dorsalCortex.json` file contains user-defined anatomical landmarks and a similarity transform that align widefield summary images to the Allen Common Coordinate Framework (CCF).

<a name="landmarks-expected-input"></a>
## Expected input (landmarks)

Required keys and structure:

- `transform`
  - A similarity transform object that maps from the source image space to the Allen CCF registered space.
- `landmarks_match`
  - Table-like structure with fields `x`, `y` (in pixels), `name`, and `color` describing landmarks in the **source image** (mean widefield image) coordinate system.
- `landmarks_im`
  - Table-like structure with fields `x`, `y` (in pixels), `name`, and `color` describing the corresponding landmarks in the **atlas/registered image** coordinate system.
- `landmarks`
  - Table-like structure with fields `x`, `y` (in mm), `name`, and `color` that holds landmarks in the Allen-registered anatomical space.

<a name="landmarks-how-data-written"></a>
## How landmarks are written to NWB

The `IBLWidefieldLandmarksInterface` performs the following steps:

- Locates the `ophys` processing module on the NWBFile and ensures that the processed widefield data (added via `IBLWidefieldSVDInterface`) have already created the `SummaryImages` container with a `MeanImage` (or other configured `source_image_name`).
- Reads the source mean image, applies the similarity transform from the JSON (`transform`), and writes the transformed image as a new `GrayscaleImage` named `MeanImageTransformed` inside an `Images` container called `TransformedImages` in the same `ophys` module.
- Creates a `Landmarks` table (from `ndx_spatial_transformation`) linking the source and transformed images and populates rows using `landmarks_match` (source coordinates) and `landmarks_im` (target/atlas coordinates); an optional `color` column is added if present.
- Builds a `SpatialTransformationMetadata` object and attaches a `SimilarityTransformation` constructed from the `transform` (rotation matrix, translation vector, and scale), and associates the `Landmarks` table with this metadata.
- Adds anatomical localization information using `ndx_anatomical_localization`: a `Localization` object, an `AllenCCFv3Space` space, and an `AnatomicalCoordinatesTable` named `CCFLocalization` that stores `[x, y, z, brain_region]` for each row in the `landmarks` table (with `z` set to NaN for dorsal cortex 2D data).

These objects are stored as lab metadata on the NWBFile and can be used downstream to interpret widefield data in Allen CCF coordinates.
