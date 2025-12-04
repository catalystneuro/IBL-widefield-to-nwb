"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.datainterfaces import SpikeGLXNIDQInterface
from neuroconv.utils import dict_deep_update, load_dict_from_file
from pynwb import read_nwb

from ibl_widefield_to_nwb.widefield2025 import WidefieldRawNWBConverter
from ibl_widefield_to_nwb.widefield2025.datainterfaces import WidefieldImagingInterface
from ibl_widefield_to_nwb.widefield2025.utils import (
    _build_nidq_metadata_from_wiring,
    _get_analog_channel_groups_from_wiring,
    _get_digital_channel_groups_from_wiring,
)


def convert_raw_session(
    nwbfile_path: str | Path,
    raw_data_dir_path: str | Path,
    cache_dir_path: str | Path,
    nidq_data_dir_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    force_cache: bool = False,
    stub_test: bool = False,
    append_on_disk_nwbfile: bool = False,
) -> Path:
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    nwbfile_path: str or Path
        Path to the output NWB file.
    raw_data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    cache_dir_path: str or Path
        Path to the directory for caching intermediate data.
    nidq_data_dir_path: str or Path
        Path to the directory containing NIDQ data.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional (calcium) imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).
    append_on_disk_nwbfile: bool, default: False
        If True, append data to an existing on-disk NWB file instead of creating a new one.

    Returns
    -------
    Path
        Path to the generated NWB file.

    """
    from ibl_widefield_to_nwb.widefield2025.conversion import (
        build_frame_cache,
        validate_cache,
    )

    data_dir_path = Path(raw_data_dir_path)
    nwbfile_path = Path(nwbfile_path)
    nwbfile_path.parent.mkdir(parents=True, exist_ok=True)

    overwrite = False
    if nwbfile_path.exists() and not append_on_disk_nwbfile:
        overwrite = True

    # ========================================================================
    # STEP 1: Build Frame Cache
    # ========================================================================

    build_frame_cache(folder_path=data_dir_path, cache_folder_path=cache_dir_path, overwrite=force_cache)
    validate_cache(cache_folder_path=cache_dir_path)

    # ========================================================================
    # STEP 2: Define data interfaces and conversion options
    # ========================================================================

    data_interfaces = dict()
    conversion_options = dict()

    # Add Imaging
    functional_imaging_interface = WidefieldImagingInterface(
        folder_path=data_dir_path,
        cache_folder_path=cache_dir_path,
        excitation_wavelength_nm=functional_wavelength_nm,
    )
    data_interfaces.update(ImagingBlue=functional_imaging_interface)

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

    isosbestic_imaging_interface = WidefieldImagingInterface(
        folder_path=data_dir_path,
        cache_folder_path=cache_dir_path,
        excitation_wavelength_nm=isosbestic_wavelength_nm,
    )
    data_interfaces.update(ImagingViolet=isosbestic_imaging_interface)
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

    # Add NIDQ
    wiring_file_name = "_spikeglx_ephysData_g0_t0.nidq.wiring.json"
    wiring_file_paths = list(nidq_data_dir_path.parent.glob(wiring_file_name))
    if len(wiring_file_paths) != 1:
        raise FileNotFoundError(
            f"Expected exactly one wiring json file ('{wiring_file_name}'), found {len(wiring_file_paths)} files."
        )
    wiring_file_path = str(wiring_file_paths[0])
    wiring = json.load(open(wiring_file_path, "r"))

    analog_channel_groups = _get_analog_channel_groups_from_wiring(wiring=wiring)
    digital_channel_groups = _get_digital_channel_groups_from_wiring(wiring=wiring)
    nidq_interface = SpikeGLXNIDQInterface(
        folder_path=nidq_data_dir_path,
        analog_channel_groups=analog_channel_groups,
        digital_channel_groups=digital_channel_groups,
    )

    data_interfaces.update(NIDQ=nidq_interface)
    conversion_options.update(
        dict(
            NIDQ=dict(
                stub_test=stub_test,
            )
        )
    )

    # Add Behavior
    # source_data.update(dict(Behavior=dict()))
    # conversion_options.update(dict(Behavior=dict()))

    # ========================================================================
    # STEP 3: Create converter
    # ========================================================================

    converter = WidefieldRawNWBConverter(
        data_interfaces=data_interfaces,
        processed_data_folder_path=processed_data_dir_path,
    )

    # ========================================================================
    # STEP 4: Get metadata
    # ========================================================================

    # Add datetime to conversion
    metadata = converter.get_metadata()
    date = datetime.datetime(year=2020, month=1, day=1, tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = date

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent.parent / "_metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update nidq metadata with wiring info
    nidq_metadata_path = Path(__file__).parent.parent / "_metadata" / "widefield_nidq_metadata.yaml"
    nidq_device_metadata = load_dict_from_file(nidq_metadata_path)

    # Dynamically build metadata based on wiring.json (maps devices to actual channel IDs)
    nidq_metadata = _build_nidq_metadata_from_wiring(wiring=wiring, device_metadata=nidq_device_metadata)
    metadata = dict_deep_update(metadata, nidq_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # ========================================================================
    # STEP 5: Write NWB file to disk
    # ========================================================================

    print(f"Writing to NWB '{nwbfile_path}' ...")
    conversion_start = time.time()

    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        append_on_disk_nwbfile=append_on_disk_nwbfile,
        overwrite=overwrite,
    )

    nwbfile = read_nwb(nwbfile_path)
    print(nwbfile.acquisition)

    conversion_time = time.time() - conversion_start

    # Calculate total size
    total_size_bytes = nwbfile_path.stat().st_size
    total_size_gb = total_size_bytes / (1024**3)

    print(f"Conversion completed in {int(conversion_time // 60)}:{conversion_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({nwbfile_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return nwbfile_path
