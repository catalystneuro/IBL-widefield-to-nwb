from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from pydantic import DirectoryPath
from roiextractors import SegmentationExtractor


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

        imaging_light_source_properties = self.get_imaging_light_source_properties()
        if len(imaging_light_source_properties) == 0:
            raise ValueError(f"No properties found for excitation wavelength '{self.excitation_wavelength_nm}' nm.")
        self.channel_id = imaging_light_source_properties["channel_id"]
        suffix = "calcium" if excitation_wavelength_nm == 470 else "isosbestic"
        self._channel_names = [f"optical_channel_{suffix}"]

        # This is available for both channels
        all_times = self._load_times()
        imaging_indices = self.get_imaging_indices()
        self._times = all_times[imaging_indices]
        # widefieldSVT.uncorrected.54b4c57c-b25c-4eb9-9d0f-76654d84a005.npy
        all_roi_response_raw = self._load_roi_response_raw()
        # Originally this is (num_rois, num_timepoints), we transpose to (num_timepoints, num_rois)
        self._roi_response_raw = all_roi_response_raw[:, imaging_indices].T
        self._num_rois = self._roi_response_raw.shape[-1]
        # widefieldChannels.frameAverage.4b030254-be6d-4e8a-bf40-8316df71b710.npy
        mean_image = self._load_mean_image()
        self._image_mean = mean_image[imaging_indices[0], ...]

        # TODO: how to solve that this should only be loaded for the functional channel
        self._roi_response_dff = None
        self._image_masks = None
        if imaging_light_source_properties["wavelength"] == 470:
            # widefieldSVT.haemoCorrected.fb72c7a7-6165-4931-9d6e-3600b26ea525.npy
            roi_response_dff = self._load_roi_response_dff()
            # This is again (num_rois, num_timepoints), we transpose to (num_timepoints, num_rois)
            self._roi_response_dff = roi_response_dff.T

            # widefieldU.images.75628fe6-1c05-4a62-96c9-0478ebfa42b0.npy
        # TODO: how to add image mask for other channel?
        all_images = self._load_images()
        self._image_masks = all_images
        self._properties = {}

    # TODO: replace with loading from ONE API
    def _load_times(self) -> np.ndarray:
        times_file_name = "imaging.times.npy"
        all_imaging_times = np.load(self.folder_path / times_file_name)
        return all_imaging_times

    # TODO: replace with loading from ONE API
    def _load_imaging_light_source_properties(self) -> pd.DataFrame:
        file_name = "imagingLightSource.properties.htsv"
        all_imaging_light_source_properties = pd.read_csv(self.folder_path / file_name)
        return all_imaging_light_source_properties

    # TODO: replace with loading from ONE API
    def _load_roi_response_raw(self) -> np.ndarray:
        file_name = "widefieldSVT.uncorrected.npy"
        all_roi_response_raw = np.load(self.folder_path / file_name)
        return all_roi_response_raw

    def _load_roi_response_dff(self) -> np.ndarray:
        file_name = "widefieldSVT.haemoCorrected.npy"
        all_roi_response_dff = np.load(self.folder_path / file_name)
        return all_roi_response_dff

    def _load_mean_image(self):
        file_name = "widefieldChannels.frameAverage.npy"
        all_mean_image = np.load(self.folder_path / file_name)
        return all_mean_image

    def _load_images(self):
        file_name = "widefieldU.images.npy"
        all_images = np.load(self.folder_path / file_name)
        return all_images

    def _load_imaging_light_source(self) -> np.ndarray:
        file_name = "imaging.imagingLightSource.npy"
        return np.load(self.folder_path / file_name, allow_pickle=True)

    def get_imaging_light_source_properties(self) -> Dict[str, Any]:
        all_imaging_light_source_properties = self._load_imaging_light_source_properties()
        this_properties = all_imaging_light_source_properties[
            all_imaging_light_source_properties["wavelength"] == self.excitation_wavelength_nm
        ]
        return this_properties.to_dict(orient="records")[0]

    def get_imaging_indices(self) -> np.ndarray:
        """Get the imaging indices for the selected channel.

        Returns
        -------
        imaging_indices: np.ndarray
            1-D array of imaging indices.
        """
        light_sources = self._load_imaging_light_source()
        imaging_indices = np.where(light_sources == self.channel_id)[0]
        return imaging_indices

    def get_num_rois(self) -> int:
        """Get total number of Regions of Interest (ROIs) in the acquired images.

        Returns
        -------
        num_rois: int
            The number of ROIs extracted.
        """
        return self._num_rois

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
        times_file_name = "imaging.times.npy"
        all_times = np.load(self.folder_path / times_file_name)
        light_source_file_name = "imaging.imagingLightSource.npy"

        light_sources = np.load(self.folder_path / light_source_file_name)
        native_timestamps = all_times[light_sources == self.channel_id]

        # Set defaults
        if start_sample is None:
            start_sample = 0
        if end_sample is None:
            end_sample = len(native_timestamps)

        return native_timestamps[start_sample:end_sample]

    def get_frame_shape(self) -> tuple[int, int]:
        """Get frame size of movie (height, width).

        Returns
        -------
        frame_shape: array_like
            2-D array: image height x image width
        """
        return self._image_mean.shape
