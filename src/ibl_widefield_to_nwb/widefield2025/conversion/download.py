import shutil
from pathlib import Path

from ibl_widefield_to_nwb.widefield2025.datainterfaces import (
    IblNIDQInterface,
    IblWidefieldLandmarksInterface,
    WidefieldImagingInterface,
    WidefieldSVDInterface,
)


def download_widefield_session(
    eid: str,
    one=None,
    mode: str = "raw",
    redownload_data: bool = False,
) -> list:
    """
    Download all datasets for a session.

    Parameters
    ----------
    eid: str
        The session ID.
    one: ONE
        An instance of the ONE API to access data.
    mode: str, default: "raw"
        Mode of data to download. Options are "raw" or "processed".
    redownload_data: bool, default: False
        If True, redownload data from ONE even if it already exists locally.

    Returns
    -------
    list
        List of paths to the downloaded files.
    """

    if one is None:
        raise ValueError("ONE instance must be provided.")

    session_folder = Path(one.cache_dir)
    cached_files = list(one.cache_dir.rglob("*"))
    if redownload_data and len(cached_files) > 0:
        print(f"Redownloading data for session '{eid}'. Clearing cache directory first.")
        shutil.rmtree(session_folder)
        session_folder.mkdir(parents=True, exist_ok=True)

    widefield_session_files = []
    match mode:
        case "raw":
            # Raw widefield imaging data
            raw_widefield_files = WidefieldImagingInterface.download_data(one=one, eid=eid, download_only=True)
            widefield_session_files.extend(raw_widefield_files)

            # NIDQ data
            nidq_files = IblNIDQInterface.download_data(one=one, eid=eid, download_only=True)
            widefield_session_files.extend(nidq_files)

        case "processed":
            # Processed widefield imaging data
            processed_widefield_files = WidefieldSVDInterface.download_data(one=one, eid=eid, download_only=True)
            widefield_session_files.extend(processed_widefield_files)

            # Landmarks data
            landmarks_files = IblWidefieldLandmarksInterface.download_data(one=one, eid=eid, download_only=True)
            widefield_session_files.extend(landmarks_files)

        case _:
            raise ValueError(f"Mode '{mode}' not recognized. Use 'raw' or 'processed'.")

    # Calculate total size
    total_size_bytes = 0
    if one.cache_dir.exists():
        for file_path in widefield_session_files:
            if file_path.is_file():
                total_size_bytes += file_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)
    print(f"Total data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return widefield_session_files
