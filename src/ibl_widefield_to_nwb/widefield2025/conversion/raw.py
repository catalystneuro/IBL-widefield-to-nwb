"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldRawNWBConverter
from ibl_widefield_to_nwb.widefield2025.conversion import (
    build_frame_cache,
    validate_cache,
)


def _get_channel_id_from_wavelength(
    excitation_wavelength_nm: int,
    light_source_properties_file_path: Path,
) -> int:
    """
    Get the channel ID corresponding to a specific wavelength.
    Parameters
    ----------
    excitation_wavelength_nm : int
        The excitation wavelength in nanometers.
    light_source_properties_file_path : Path
        Path to the .htsv file containing light source properties.
    Returns
    -------
    int
        The channel ID corresponding to the specified wavelength.
    """
    light_sources = pd.read_csv(light_source_properties_file_path)
    channel_id = light_sources.loc[light_sources["wavelength"] == excitation_wavelength_nm, "channel_id"].tolist()
    if len(channel_id) == 0:
        raise ValueError(f"No channel ID found for wavelength {excitation_wavelength_nm} nm.")
    return channel_id[0]


def _get_imaging_times_by_channel_id(
    aligned_times_file_path: Path,
    light_source_file_path: Path,
    channel_id: int,
) -> np.ndarray:
    """
    Get imaging times for a specific channel ID.
    Parameters
    ----------
    aligned_times_file_path : Path
        Path to the .npy file containing aligned imaging times.
    light_source_file_path : Path
        Path to the .npy file containing light source channel IDs.
    channel_id : int
        The channel ID for which to retrieve imaging times.
    Returns
    -------
    np.ndarray
        Array of imaging times corresponding to the specified channel ID.
    """
    all_times = np.load(aligned_times_file_path)
    light_sources = np.load(light_source_file_path)

    times_per_channel_id = all_times[light_sources == channel_id]
    return times_per_channel_id


def convert_raw_session(
    raw_data_dir_path: str | Path,
    cache_dir_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    output_dir_path: str | Path,
    force_cache: bool = False,
    stub_test: bool = False,
) -> Path:
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    raw_data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    cache_dir_path: str or Path
        Path to the directory for caching intermediate data.
    output_dir_path: str or Path
        Path to the directory where the output NWB file will be saved.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional (calcium) imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

    Returns
    -------
    Path
        Path to the generated NWB file.

    """

    data_dir_path = Path(raw_data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    session_id = "subject_identifier_usually"
    nwbfile_path = output_dir_path / f"{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # ========================================================================
    # STEP 1: Build Frame Cache
    # ========================================================================

    build_frame_cache(folder_path=data_dir_path, cache_folder_path=cache_dir_path, overwrite=force_cache)
    validate_cache(cache_folder_path=cache_dir_path)

    # ========================================================================
    # STEP 2: Define source data and conversion options
    # ========================================================================

    # Add Imaging
    source_data.update(
        dict(
            ImagingBlue=dict(
                folder_path=data_dir_path,
                cache_folder_path=cache_dir_path,
                excitation_wavelength_nm=functional_wavelength_nm,
            )
        )
    )
    conversion_options.update(
        dict(
            ImagingBlue=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=0,
                stub_test=stub_test,
                iterator_options=dict(
                    display_progress=True,
                    progress_bar_options=dict(desc="Writing raw imaging data for functional channel..."),
                ),
            )
        )
    )
    source_data.update(
        dict(
            ImagingViolet=dict(
                folder_path=data_dir_path,
                cache_folder_path=cache_dir_path,
                excitation_wavelength_nm=isosbestic_wavelength_nm,
            )
        )
    )
    conversion_options.update(
        dict(
            ImagingViolet=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=1,
                stub_test=stub_test,
                iterator_options=dict(
                    display_progress=True,
                    progress_bar_options=dict(desc="Writing raw imaging data for isosbestic channel..."),
                ),
            )
        )
    )

    # Add Behavior
    # source_data.update(dict(Behavior=dict()))
    # conversion_options.update(dict(Behavior=dict()))

    # ========================================================================
    # STEP 3: Create converter
    # ========================================================================

    converter = WidefieldRawNWBConverter(source_data=source_data)

    # ========================================================================
    # STEP 4: Align times
    # ========================================================================

    # Get imaging times and add to conversion options
    aligned_times_file_path = processed_data_dir_path / "imaging.times.npy"
    light_source_file_path = processed_data_dir_path / "imaging.imagingLightSource.npy"
    light_source_properties_file_path = processed_data_dir_path / "imagingLightSource.properties.htsv"
    functional_channel_id = _get_channel_id_from_wavelength(
        excitation_wavelength_nm=functional_wavelength_nm,
        light_source_properties_file_path=light_source_properties_file_path,
    )
    functional_imaging_times = _get_imaging_times_by_channel_id(
        aligned_times_file_path=aligned_times_file_path,
        light_source_file_path=light_source_file_path,
        channel_id=functional_channel_id,
    )
    converter.data_interface_objects["ImagingBlue"].imaging_extractor.set_times(times=functional_imaging_times)

    isosbestic_channel_id = _get_channel_id_from_wavelength(
        excitation_wavelength_nm=isosbestic_wavelength_nm,
        light_source_properties_file_path=light_source_properties_file_path,
    )
    isosbestic_imaging_times = _get_imaging_times_by_channel_id(
        aligned_times_file_path=aligned_times_file_path,
        light_source_file_path=light_source_file_path,
        channel_id=isosbestic_channel_id,
    )
    converter.data_interface_objects["ImagingViolet"].imaging_extractor.set_times(times=isosbestic_imaging_times)

    # ========================================================================
    # STEP 5: Get metadata
    # ========================================================================

    # Add datetime to conversion
    metadata = converter.get_metadata()
    date = datetime.datetime(year=2020, month=1, day=1, tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = date

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent.parent / "metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update ophys metadata
    ophys_metadata_path = Path(__file__).parent.parent / "metadata" / "widefield_ophys_metadata.yaml"
    ophys_metadata = load_dict_from_file(ophys_metadata_path)
    metadata = dict_deep_update(metadata, ophys_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # ========================================================================
    # STEP 6: Write NWB file to disk
    # ========================================================================

    print(f"Writing to NWB '{nwbfile_path}' ...")
    conversion_start = time.time()
    # Run conversion
    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        overwrite=True,
    )

    conversion_time = time.time() - conversion_start

    # Calculate total size
    total_size_bytes = Path(nwbfile_path).stat().st_size
    total_size_gb = total_size_bytes / (1024**3)

    print(f"Conversion completed in {int(conversion_time // 60)}:{conversion_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({nwbfile_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return nwbfile_path
