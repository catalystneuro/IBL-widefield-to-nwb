import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import DirectoryPath, FilePath
from roiextractors import ImagingExtractor


class WidefieldImagingExtractor(ImagingExtractor):
    """
    ImagingExtractor for IBL widefield data that reads from a disk-backed memory-mapped cache.

    This extractor expects a cache folder produced by build_frame_cache(...) containing:
      - frames.dat : a numpy memmap file with shape (n_frames, height, width) storing grayscale frames (e.g. uint8)
      - meta.json   : metadata with keys: total_num_samples, height, width, dtype, fps

    The extractor also requires:
      - htsv_file_path : path to the HTSV describing LED/channel properties
      - camlog_file_path: path to the camera log containing "#LED:channel,frame,timestamp" lines

    Notes
    -----
    - Frames are read directly from the memmap (no OpenCV/video capture used here).
    - The memmap stores grayscale frames in (time, height, width) order.
    """

    extractor_name = "WidefieldImagingExtractor"

    def __init__(
        self,
        folder_path: DirectoryPath,
        htsv_file_path: FilePath,
        camlog_file_path: FilePath,
        excitation_wavelength_nm: Optional[int] = None,
    ):
        """
        Parameters
        ----------
        folder_path : DirectoryPath
            Path to the cache folder produced by build_frame_cache (contains frames.dat and meta.json).
        htsv_file_path : FilePath
            Path to HTSV file describing LED properties.
        camlog_file_path : FilePath
            Path to camera log file used to determine frame -> timestamp mapping.
        excitation_wavelength_nm : int, optional
            Excitation wavelength in nm to select the appropriate channel (e.g., 470 for calcium, 405 for isosbestic).
        """
        self.cache_folder = Path(folder_path)
        self.htsv_file_path = str(htsv_file_path)
        self.camlog_file_path = str(camlog_file_path)
        self.excitation_wavelength_nm = excitation_wavelength_nm or 470  # default to 470 nm if not provided

        # Load on-disk metadata
        meta_path = self.cache_folder / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"'meta.json' not found in cache folder: '{self.cache_folder}'")
        with open(meta_path, "r") as f:
            meta = json.load(f)

        # store metadata in a consistent structure
        self._video_metadata = dict(
            total_num_samples=int(meta["total_num_samples"]),
            image_shape=(meta["height"], meta["width"]),
            dtype=np.dtype(meta["dtype"]),
            sampling_frequency=float(meta.get("fps", np.nan)),
            memmap_path=str(self.cache_folder / "frames.dat"),
        )

        self._camera_log_metadata = self._get_camera_log_metadata()
        imaging_light_source_properties = self.get_imaging_light_source_properties()
        channel_id = imaging_light_source_properties["LED"]
        if len(imaging_light_source_properties) == 0:
            raise ValueError(f"No properties found for channel_id '{channel_id}'")
        self._num_channels = len(np.unique(self._camera_log_metadata["channel_id"]))
        if self._num_channels != 2:
            raise ValueError(f"Expected 2 channels in camera log, found {self._num_channels}.")
        # filter for channel_id and compute zero-indexed frame indices
        self._camera_log_metadata = self._camera_log_metadata[
            self._camera_log_metadata["channel_id"] == int(channel_id)
        ].reset_index(drop=True)
        self._frame_indices = self._camera_log_metadata["frame_id"].astype(int).to_numpy() - 1  # zero indexed

        self._channel_names = ["OpticalChannel"]
        super().__init__()

    def _load_frame_cache(self) -> np.memmap:
        """
        Load the memmap file containing cached frames.

        Returns
        -------
        np.memmap
            Memory-mapped array of shape (n_frames, height, width).
        """
        memmap_path = self._video_metadata["memmap_path"]
        total = self._video_metadata["total_num_samples"]
        height, width = self._video_metadata["image_shape"]
        dtype = self._video_metadata["dtype"]

        frames_memmap = np.memmap(memmap_path, dtype=dtype, mode="r", shape=(total, height, width))
        return frames_memmap

    def _get_camera_log_metadata(self) -> pd.DataFrame:
        """
        Parse camera log file and return a DataFrame with typed columns:
          - channel_id (int)
          - frame_id (int)
          - timestamp (float)
        """
        camera_log_data = []
        with open(self.camlog_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and line.startswith("#LED"):
                    match = re.match(r"#LED:(?P<channel_id>\d+),(?P<frame_id>\d+),(?P<timestamp>[\d\.]+)", line)
                    if match:
                        gd = match.groupdict()
                        camera_log_data.append(
                            {
                                "channel_id": int(gd["channel_id"]),
                                "frame_id": int(gd["frame_id"]),
                                "timestamp": float(gd["timestamp"]),
                            }
                        )

        # limit to available frames in the memmap, if needed
        total = self._video_metadata["total_num_samples"]
        camera_log_data = camera_log_data[:total]
        if len(camera_log_data) == 0:
            # ensure at least a minimal DataFrame shape
            return pd.DataFrame(columns=["channel_id", "frame_id", "timestamp"])
        return pd.DataFrame.from_records(camera_log_data)

    # TODO: replace with loading from ONE API
    def _load_imaging_light_source_properties(self):
        all_imaging_light_source_properties = pd.read_csv(self.htsv_file_path, sep="\t", index_col=0)
        return all_imaging_light_source_properties

    def get_imaging_light_source_properties(self) -> Dict[str, Any]:
        all_imaging_light_source_properties = self._load_imaging_light_source_properties()
        this_properties = all_imaging_light_source_properties[
            all_imaging_light_source_properties["wavelength"] == self.excitation_wavelength_nm
        ]
        return this_properties.to_dict(orient="records")[0]

    def get_image_shape(self) -> Tuple[int, int]:
        """Get the shape of the video frame (num_rows, num_columns).

        Returns
        -------
        image_shape: tuple
            Shape of the video frame (num_rows, num_columns).
        """
        return self._video_metadata["image_shape"]

    def get_num_samples(self) -> int:
        """
        Number of samples for the selected channel (i.e., number of frames for that channel).
        """
        return len(self._frame_indices)

    def get_sampling_frequency(self) -> float:
        """
        Returns the per-channel sampling rate in Hz.

        This assumes that the raw memmap fps represents the combined frame rate of all channels.
        """
        raw_fps = float(self._video_metadata["sampling_frequency"])
        return raw_fps / self._num_channels

    def get_dtype(self) -> np.dtype:
        """Return the numpy dtype of stored frames in the memmap."""
        return self._video_metadata["dtype"]

    def get_channel_names(self) -> list:
        """List of channel names for this extractor (single-channel list)."""
        return self._channel_names

    def get_series(self, start_sample: Optional[int] = None, end_sample: Optional[int] = None) -> np.ndarray:
        """
        Read a contiguous series of frames for the selected channel from the memmap.

        Returns array of shape (n_samples, height, width) with dtype == get_dtype().
        """
        start_sample = 0 if start_sample is None else start_sample
        end_sample = len(self._frame_indices) if end_sample is None else end_sample
        frame_indices = self._frame_indices[start_sample:end_sample]

        if len(frame_indices) == 0:
            raise (ValueError("No frames selected for the given start_sample and end_sample."))

        # open memmap and index into it
        frames_memmap = self._load_frame_cache()
        # index memmap with the required frame indices (fast, no re-decode)
        series = np.asarray(frames_memmap[frame_indices])
        return series

    def get_native_timestamps(
        self, start_sample: Optional[int] = None, end_sample: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Return timestamps (float seconds) for the selected channel samples.

        Returns numpy array shape (n_samples,) or None if no timestamps available.
        """
        if self._camera_log_metadata.shape[0] == 0:
            return None

        start_sample = 0 if start_sample is None else int(start_sample)
        end_sample = len(self._frame_indices) if end_sample is None else int(end_sample)

        # timestamps were parsed when building camera_log_metadata and filtered for channel in __init__
        timestamps = self._camera_log_metadata["timestamp"].to_numpy(dtype=float)
        return timestamps[start_sample:end_sample]
