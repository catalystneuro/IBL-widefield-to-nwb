"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldRawNWBConverter


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


def raw_imaging_session_to_nwb(
    raw_data_dir_path: str | Path,
    processed_data_dir_path: str | Path,
    output_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    stub_test: bool = False,
):
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    raw_data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    processed_data_dir_path: str or Path
        Path to the directory containing processed widefield data
        (e.g., imaging.times.npy, imaging.imagingLightSource.npy) for the session.
    output_dir_path: str or Path
        Path to the directory where the output NWB file will be saved.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

    """

    raw_data_dir_path = Path(raw_data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    session_id = "subject_identifier_usually"
    nwbfile_path = output_dir_path / f"{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # Add Imaging
    source_data.update(
        dict(ImagingBlue=dict(folder_path=raw_data_dir_path, excitation_wavelength_nm=functional_wavelength_nm))
    )
    conversion_options.update(
        dict(
            ImagingBlue=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=0,
                stub_test=stub_test,
                iterator_options=dict(display_progress=True),
            )
        )
    )
    source_data.update(
        dict(ImagingViolet=dict(folder_path=raw_data_dir_path, excitation_wavelength_nm=isosbestic_wavelength_nm))
    )
    conversion_options.update(
        dict(
            ImagingViolet=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=1,
                stub_test=stub_test,
                iterator_options=dict(display_progress=True),
            )
        )
    )

    # Add Behavior
    # source_data.update(dict(Behavior=dict()))
    # conversion_options.update(dict(Behavior=dict()))

    converter = WidefieldRawNWBConverter(source_data=source_data)

    # TODO: where should this go?
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

    # Add datetime to conversion
    metadata = converter.get_metadata()
    date = datetime.datetime(year=2020, month=1, day=1, tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = date

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent / "metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update ophys metadata
    ophys_metadata_path = Path(__file__).parent / "metadata" / "widefield_ophys_metadata.yaml"
    ophys_metadata = load_dict_from_file(ophys_metadata_path)
    metadata = dict_deep_update(metadata, ophys_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # Run conversion
    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        overwrite=True,
    )


if __name__ == "__main__":

    # Parameters for conversion
    raw_data_dir_path = Path("/Users/weian/data/IBL/raw_widefield_data")
    processed_data_dir_path = Path("/Users/weian/data/IBL/alf/widefield")
    output_dir_path = Path("/Volumes/T9/data/IBL")

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = True

    raw_imaging_session_to_nwb(
        raw_data_dir_path=raw_data_dir_path,
        processed_data_dir_path=processed_data_dir_path,
        output_dir_path=output_dir_path,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
    )
