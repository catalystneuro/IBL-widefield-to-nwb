import json
import tempfile
import time
from pathlib import Path

import numpy as np
from pydantic import DirectoryPath


def build_frame_cache(folder_path: DirectoryPath, cache_folder_path: DirectoryPath = None, overwrite: bool = False):
    """
    Create a disk cache of grayscale frames as a single memory-mapped array.

    This function reads a video file and writes a disk-backed memmap file `frames.dat`
    and a JSON metadata file `meta.json` into `cache_folder_path`. The memmap stores
    grayscale frames as contiguous `uint8` values with shape `(n_frames, height, width)`.

    Parameters
    ----------
    folder_path : DirectoryPath
        Path to the folder containing the `.frames.mov` video file.
    cache_folder_path : DirectoryPath, optional
        Directory to write cache; if None, a temporary directory is created and returned.
    overwrite : bool, optional
        Whether to overwrite existing cache files. Default is False.

    Notes
    -----
    - Frames are converted to grayscale via OpenCV (`cv2.cvtColor(..., cv2.COLOR_BGR2GRAY)`)
    - The memmap shape is determined from the grayscale frames. If the video reader
      reports a total frame count, that value is used to preallocate the memmap.
      If the count is unknown or incorrect, the function will stop when frames
      are exhausted and `meta.json` will record the actual number of frames written.
    """
    import cv2
    from neuroconv.datainterfaces.behavior.video.video_utils import VideoCaptureContext

    print(f"Building frame cache at {cache_folder_path} ...")
    frame_cache_start = time.time()

    cache_folder_path = Path(cache_folder_path or tempfile.mkdtemp(prefix="wf_cache_"))
    cache_folder_path.mkdir(parents=True, exist_ok=True)
    data_path = cache_folder_path / "frames.dat"
    meta_path = cache_folder_path / "meta.json"

    if data_path.exists() and not overwrite:
        print(f"Frame cache already exists at {cache_folder_path}, skipping rebuild.")
        return cache_folder_path

    movie_file_paths = list(folder_path.glob("*.frames.mov"))
    if len(movie_file_paths) == 0:
        raise FileNotFoundError(f"No .frames.mov files found in folder: {folder_path}")
    elif len(movie_file_paths) > 1:
        raise ValueError(
            f"Multiple .frames.mov files found in folder: {folder_path}. Please ensure only one file is present."
        )
    movie_file_path = movie_file_paths[0]

    video_capture_ob = VideoCaptureContext(movie_file_path)

    total_num_samples = video_capture_ob.get_video_frame_count()
    # OpenCV returns frame shape as (height, width, color channels)
    height, width, _ = video_capture_ob.get_frame_shape()
    frame_dtype = video_capture_ob.get_video_frame_dtype()
    frame_rate = video_capture_ob.get_video_fps()

    # allocate memmap for grayscale uint8 frames: shape (n_frames, H, W)
    mem = np.memmap(str(data_path), dtype=frame_dtype, mode="w+", shape=(total_num_samples, height, width))

    frame_index = 0
    while frame_index < total_num_samples:
        try:
            frame = next(video_capture_ob)
        except StopIteration:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mem[frame_index] = gray
        frame_index += 1

    # flush and release
    mem.flush()
    video_capture_ob.release()

    # store metadata (note: timestamps are not handled here; add camlog parsing if needed)
    meta = {
        "total_num_samples": frame_index,
        "height": height,
        "width": width,
        "dtype": str(frame_dtype),
        "fps": frame_rate,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    frame_cache_time = time.time() - frame_cache_start

    # Calculate total size
    total_size_bytes = Path(movie_file_path).stat().st_size
    cache_size_bytes = data_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)
    cache_size_gb = cache_size_bytes / (1024**3)

    print(f"Writing frame cache completed in {int(frame_cache_time // 60)}:{frame_cache_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({movie_file_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")
    print(f"Cache data ({data_path}) size: {cache_size_gb:.2f} GB ({cache_size_bytes:,} bytes)")
    return None
