from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import DirectoryPath
from roiextractors import SegmentationExtractor
from roiextractors.segmentationextractor import _ROIMasks, _RoiResponse


class WidefieldSegmentationExtractor(SegmentationExtractor):
    """A segmentation extractor for IBL Widefield processed data."""

    extractor_name = "WidefieldSegmentationExtractor"

    def __init__(self, folder_path: DirectoryPath, excitation_wavelength_nm: int):
        """Initialize a WidefieldSegmentationExtractor instance.

        Main class for extracting segmentation data from .npy format.

        Expected file structure:
        folder_path/
            ├── imaging.imagingLightSource.npy
            ├── imaging.times.npy
            ├── imagingLightSource.properties.htsv
            ├── widefieldChannels.frameAverage.npy
            ├── widefieldSVT.haemoCorrected.npy
            ├── widefieldSVT.uncorrected.npy
            └── widefieldU.images.npy

        Parameters
        ----------
        folder_path: str or Path
            Path to the folder containing segmentation data files.
        excitation_wavelength_nm: int
            The excitation wavelength (in nm) for the channel to load.
        """
        super().__init__()

        self.folder_path = Path(folder_path)
        self.excitation_wavelength_nm = excitation_wavelength_nm

        # Timestamps (both channels)
        self._timestamps_file_name = "imaging.times.npy"
        # Imaging light source properties (contains channel ids for each wavelength)
        self._imaging_light_source_properties_file_name = "imagingLightSource.properties.htsv"
        self._imaging_light_source_file_name = "imaging.imagingLightSource.npy"
        # Raw traces (both channels)
        self._raw_traces_file_name = "widefieldSVT.uncorrected.npy"
        # Corrected traces (only calcium channel)
        self._corrected_traces_file_name = "widefieldSVT.haemoCorrected.npy"
        # ROI masks (same for both channels)
        self._ROI_masks_file_name = "widefieldU.images.npy"
        # summary images (both channels)
        self._mean_image_file_name = "widefieldChannels.frameAverage.npy"

        # Contains channel_id, color, wavelength information for the selected excitation wavelength
        imaging_light_source_properties = self.get_imaging_light_source_properties()
        if len(imaging_light_source_properties) == 0:
            raise ValueError(f"No properties found for excitation wavelength '{self.excitation_wavelength_nm}' nm.")
        self.channel_id = imaging_light_source_properties["channel_id"]
        self._channel_names = ["OpticalChannel"]

        # This is available for both channels
        all_times = self._load_times()
        self._frames_indices = self.get_frame_indices()
        self._times = all_times[self._frames_indices]

        # ROI masks (height, width, n_rois)
        all_image_masks = self._load_images()
        cell_ids = self.get_roi_ids()
        roi_id_map = {roi_id: index for index, roi_id in enumerate(cell_ids)}
        self._frame_shape = self.get_frame_shape()
        self._roi_masks = _ROIMasks(
            data=all_image_masks,
            mask_tpe="nwb-image_mask",
            field_of_view_shape=self._frame_shape,
            roi_id_map=roi_id_map,
        )
        self._properties = {}

    # TODO: replace with loading from ONE API
    def _load_times(self) -> np.ndarray:
        all_imaging_times = np.load(self.folder_path / self._timestamps_file_name)
        return all_imaging_times

    # TODO: replace with loading from ONE API
    def _load_imaging_light_source_properties(self) -> pd.DataFrame:
        all_imaging_light_source_properties = pd.read_csv(
            self.folder_path / self._imaging_light_source_properties_file_name
        )
        return all_imaging_light_source_properties

    # TODO: replace with loading from ONE API
    def _load_roi_response_raw(self) -> np.ndarray:
        all_roi_response_raw = np.load(self.folder_path / self._raw_traces_file_name)
        return all_roi_response_raw

    # TODO: replace with loading from ONE API
    def _load_roi_response_dff(self) -> np.ndarray:
        all_roi_response_dff = np.load(self.folder_path / self._corrected_traces_file_name)
        return all_roi_response_dff

    # TODO: replace with loading from ONE API
    def _load_mean_image(self) -> np.ndarray:
        mean_images = np.load(self.folder_path / self._mean_image_file_name)
        first_frame_index = self._frames_indices[0]
        mean_image = mean_images[first_frame_index, ...]
        return mean_image

    # TODO: replace with loading from ONE API
    def _load_images(self):
        all_images = np.load(self.folder_path / self._ROI_masks_file_name)
        return all_images

    # TODO: replace with loading from ONE API
    def _load_imaging_light_source(self) -> np.ndarray:
        return np.load(self.folder_path / self._imaging_light_source_file_name, allow_pickle=True)

    # TODO: replace with loading from ONE API
    def get_imaging_light_source_properties(self) -> Dict[str, Any]:
        all_imaging_light_source_properties = self._load_imaging_light_source_properties()
        this_properties = all_imaging_light_source_properties[
            all_imaging_light_source_properties["wavelength"] == self.excitation_wavelength_nm
        ]
        return this_properties.to_dict(orient="records")[0]

    def get_frame_indices(self) -> np.ndarray:
        """Get the frame indices for the selected channel.

        Returns
        -------
        imaging_indices: np.ndarray
            1-D array of frame indices.
        """
        light_sources = self._load_imaging_light_source()
        frame_indices = np.where(light_sources == self.channel_id)[0]
        return frame_indices

    def get_accepted_list(self) -> list:
        """Get a list of accepted ROI ids.

        Returns
        -------
        accepted_list: list
            List of accepted ROI ids.
        """
        return list(range(self.get_num_rois()))

    def get_rejected_list(self) -> list:
        """Get a list of rejected ROI ids.

        Returns
        -------
        rejected_list: list
            List of rejected ROI ids.
        """
        return []

    def get_native_timestamps(
        self, start_sample: Optional[int] = None, end_sample: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """Get the original timestamps from the data source.

        Parameters
        ----------
        start_sample : int, optional
            Start sample index (inclusive).
        end_sample : int, optional
            End sample index (exclusive).

        Returns
        -------
        timestamps : np.ndarray or None
            The original timestamps in seconds, or None if not available.
        """
        all_times = np.load(self.folder_path / self._timestamps_file_name)
        light_sources = np.load(self.folder_path / self._imaging_light_source_file_name)

        native_timestamps = all_times[light_sources == self.channel_id]

        # Set defaults
        if start_sample is None:
            start_sample = 0
        if end_sample is None:
            end_sample = len(native_timestamps)

        return native_timestamps[start_sample:end_sample]

    def get_frame_shape(self) -> tuple[int, int]:
        """Get the shape of the frames in the recording.

        Returns
        -------
        frame_shape: tuple[int, int]
            Shape of the frames in the recording.
        """
        if not hasattr(self, "_frame_shape"):
            image_mean = self._load_mean_image()
            assert image_mean is not None, f"{self._mean_image_file_name} is required but could not be loaded"
            self._frame_shape = (image_mean.shape[0], image_mean.shape[1])
        return self._frame_shape

    def _get_rois_responses(self) -> List[_RoiResponse]:
        """Load the ROI responses from uncorrected and corrected files.
        Returns
        -------
        _roi_responses: List[_RoiResponse]
            List of _RoiResponse objects containing the ROI responses.
        """
        if not self._roi_responses:
            self._roi_responses = []

            # This loads the raw traces for all channels
            raw_traces = self._load_roi_response_raw()
            # Originally this is (num_rois, num_timepoints), we transpose to (num_timepoints, num_rois)
            frame_indices = self.get_frame_indices()
            raw_traces = raw_traces[:, frame_indices].T

            cell_ids = list(range(raw_traces.shape[1]))
            self._roi_responses.append(_RoiResponse("raw", raw_traces, cell_ids))

            if self.excitation_wavelength_nm == 470:
                # widefieldSVT.haemoCorrected.npy
                dff_traces = self._load_roi_response_dff()
                # This is again (num_rois, num_timepoints), we transpose to (num_timepoints, num_rois)
                dff_traces = dff_traces.T
                self._roi_responses.append(_RoiResponse("dff", dff_traces, list(cell_ids)))

        return self._roi_responses

    def get_traces_dict(self) -> dict:
        """Get traces as a dictionary with key as the name of the ROiResponseSeries.

        Returns
        -------
        _roi_response_dict: dict
            dictionary with key, values representing different types of RoiResponseSeries:
                Raw Fluorescence, DeltaFOverF, Denoised, Neuropil, Deconvolved, Background, etc.
        """
        if not self._roi_responses:
            self._get_rois_responses()

        traces = {response.response_type: response.data for response in self._roi_responses}
        return traces

    def get_images_dict(self) -> dict:
        """Get images as a dictionary with key as the name of the ROIResponseSeries.

        Returns
        -------
        _summary_images: dict
            dictionary with key, values representing different types of Images used in segmentation:
                Mean, Correlation image, Maximum projection, etc.
        """
        if not self._summary_images:
            self._summary_images = {}
            mean_image = self._load_mean_image()
            if mean_image is not None:
                self._summary_images["mean"] = mean_image
        return self._summary_images
