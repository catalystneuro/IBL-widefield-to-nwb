import re
from typing import Tuple, Optional, Dict, Any

import numpy as np
import pandas as pd
from neuroconv.datainterfaces.behavior.video.video_utils import VideoCaptureContext
from neuroconv.tools import get_package
from roiextractors import ImagingExtractor

class WidefieldImagingExtractor(ImagingExtractor):
    """A segmentation extractor for IBL Widefield raw imaging data (.mov)."""

    extractor_name = "WidefieldImagingExtractor"

    def __init__(self, file_path: str, htsv_file_path: str, camlog_file_path: str, channel_id: Optional[int] = None):
        """Initialize a WidefieldImagingExtractor instance.

        Main class for extracting raw imaging data from .mov format.

        Parameters
        ----------
        file_path: str or Path
            Path to the .mov file containing raw imaging data.
        """
        super().__init__()
        self.file_path = str(file_path)
        self.htsv_file_path = str(htsv_file_path)
        self.channel_id = channel_id or 2


        self._video_capture = VideoCaptureContext
        self._cv2 = get_package(package_name="cv2", installation_instructions="pip install opencv-python-headless")

        self._video_metadata = self._get_video_metadata()
        self.camlog_file_path = camlog_file_path
        self._camera_log_metadata = self._get_camera_log_metadata()
        imaging_light_source_properties = self.get_imaging_light_source_properties()
        if len(imaging_light_source_properties) == 0:
            raise ValueError(f"No properties found for channel_id '{self.channel_id}'")

        # filter for channel_id
        self._camera_log_metadata = self._camera_log_metadata[self._camera_log_metadata["channel_id"] == str(channel_id)]
        self._frame_indices = self._camera_log_metadata["frame_id"].astype(int).to_numpy() - 1  # zero indexed


        suffix = "calcium" if imaging_light_source_properties["wavelength"] == 470 else "isosbestic"
        self._channel_names = [f"optical_channel_{suffix}"]


    def _get_video_metadata(self) -> dict:
        """Get metadata from the video file using VideoCaptureContext.
        Returns
        -------
        metadata: dict
            Dictionary containing video metadata such as total_frames, frame_shape, dtype, and rate.
        """
        with self._video_capture(self.file_path) as video_capture_ob:
            return dict(
                total_num_samples=video_capture_ob.get_video_frame_count(),
                image_shape=video_capture_ob.get_frame_shape(),
                dtype=video_capture_ob.get_video_frame_dtype(),
                sampling_frequency=video_capture_ob.get_video_fps(),
            )

    def _get_camera_log_metadata(self) -> pd.DataFrame:
        camera_log_data = []
        with open(self.camlog_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and line.startswith('#LED'):
                    # regex match #LED:{channel_id},{frame_id},{timestamp}
                    match = re.match(r"#LED:(?P<channel_id>\d+),(?P<frame_id>\d+),(?P<timestamp>[\d\.]+)", line)
                    if match:
                        camera_log_data.append(match.groupdict())

        camera_log_data = camera_log_data[:self._video_metadata["total_num_samples"]]
        return pd.DataFrame.from_dict(camera_log_data)


    # TODO: replace with loading from ONE API
    def _load_imaging_light_source_properties(self):
        all_imaging_light_source_properties = pd.read_csv(self.htsv_file_path, sep="\t", index_col=0)
        return all_imaging_light_source_properties

    def get_imaging_light_source_properties(self) -> Dict[str, Any]:
        all_imaging_light_source_properties = self._load_imaging_light_source_properties()
        this_properties = all_imaging_light_source_properties[all_imaging_light_source_properties["LED"] == self.channel_id]
        return this_properties.to_dict(orient="records")[0]


    def get_image_shape(self) -> Tuple[int, int]:
        """Get the shape of the video frame (num_rows, num_columns).

        Returns
        -------
        image_shape: tuple
            Shape of the video frame (num_rows, num_columns).
        """
        return self._video_metadata["image_shape"][:-1]

    def get_num_samples(self) -> int:
        """Get the number of samples in the video.

        Returns
        -------
        num_samples: int
            Number of samples in the video.
        """
        return self._video_metadata["total_num_samples"] // 2

    def get_sampling_frequency(self) -> float:
        """Get the sampling frequency in Hz.

        Returns
        -------
        sampling_frequency: float
            Sampling frequency in Hz.
        """
        return self._video_metadata["sampling_frequency"] // 2

    def get_dtype(self) -> np.dtype:
        """Get the data type of the video frames.

        Returns
        -------
        dtype: numpy.dtype
            Data type of the video frames.
        """
        return self._video_metadata["dtype"]

    def get_channel_names(self) -> list:
        """Get the channel names in the recoding.

        Returns
        -------
        channel_names: list
            List of strings of channel names
        """
        return self._channel_names

    def get_series(self, start_sample: Optional[int] = None, end_sample: Optional[int] = None) -> np.ndarray:
        """Get the series of samples.

        Parameters
        ----------
        start_sample: int, optional
            Start sample index (inclusive).
        end_sample: int, optional
            End sample index (exclusive).

        Returns
        -------
        series: numpy.ndarray
            The series of samples.

        Notes
        -----
        Importantly, we follow the convention that the dimensions of the array are returned in their matrix order,
        More specifically:
        (time, height, width)

        Which is equivalent to:
        (samples, rows, columns)

        For volumetric data, the dimensions are:
        (time, height, width, planes)

        Which is equivalent to:
        (samples, rows, columns, planes)

        Note that this does not match the cartesian convention:
        (t, x, y)

        Where x is the columns width or and y is the rows or height.
        """
        # Use only the frame indices for the selected channel
        frame_indices = self._frame_indices

        start_sample = start_sample or 0
        end_sample = end_sample or len(frame_indices)
        frame_indices = frame_indices[start_sample:end_sample]

        series = np.empty(shape=(len(frame_indices), *self.get_sample_shape()), dtype=self.get_dtype())
        with self._video_capture(file_path=str(self.file_path)) as video_obj:
            for i, frame_idx in enumerate(frame_indices):
                video_obj.current_frame = frame_idx
                frame = next(video_obj)
                series[i] = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2GRAY)

        return series

    def get_native_timestamps(
        self, start_sample: Optional[int] = None, end_sample: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Retrieve the original unaltered timestamps for the data in this interface.

        This function should retrieve the data on-demand by re-initializing the IO.
        Can be overridden to return None if the extractor does not have native timestamps.

        Parameters
        ----------
        start_sample : int, optional
            The starting sample index. If None, starts from the beginning.
        end_sample : int, optional
            The ending sample index. If None, goes to the end.

        Returns
        -------
        timestamps: numpy.ndarray or None
            The timestamps for the data stream, or None if native timestamps are not available.
        """
        # Set defaults
        if start_sample is None:
            start_sample = 0
        if end_sample is None:
            end_sample = self._video_metadata["total_num_samples"]

        return np.array(self._camera_log_metadata[start_sample:end_sample])
