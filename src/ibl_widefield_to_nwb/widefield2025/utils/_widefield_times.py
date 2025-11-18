from pathlib import Path

import numpy as np
import pandas as pd


def _get_channel_id_from_wavelength(
    excitation_wavelength_nm: int,
    light_source_properties_file_path: Path | str,
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
    channel_ids = light_sources.loc[light_sources["wavelength"] == excitation_wavelength_nm, "channel_id"].tolist()
    if len(channel_ids) == 0:
        raise ValueError(f"No channel ID found for wavelength {excitation_wavelength_nm} nm.")
    return channel_ids[0]


def _get_imaging_times_by_excitation_wavelength_nm(
    excitation_wavelength_nm: int,
    aligned_times_file_path: Path | str,
    light_source_properties_file_path: Path | str,
    light_source_file_path: Path | str,
) -> np.ndarray:
    """
    Get imaging times for a specific excitation wavelength.

    Parameters
    ----------
    excitation_wavelength_nm : int
        The excitation wavelength in nanometers.
    aligned_times_file_path : Path
        Path to the .npy file ("imaging.times.npy") containing aligned imaging times.
    light_source_file_path : Path
        Path to the .npy file ("imaging.imagingLightSource.npy") containing light source channel IDs.
    light_source_properties_file_path : Path
        Path to the .htsv file ("imagingLightSource.properties.htsv") containing light source properties like
        channel ID, color, wavelength.
    Returns
    -------
    np.ndarray
        Array of imaging times corresponding to the specified channel ID.
    """

    channel_id = _get_channel_id_from_wavelength(
        excitation_wavelength_nm=excitation_wavelength_nm,
        light_source_properties_file_path=light_source_properties_file_path,
    )

    all_times = np.load(aligned_times_file_path)
    light_sources = np.load(light_source_file_path)

    times_per_channel_id = all_times[light_sources == channel_id]
    return times_per_channel_id
