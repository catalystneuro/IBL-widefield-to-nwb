"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path

from ibl_widefield_to_nwb.widefield2025.conversion import convert_processed_session


def session_to_nwb(
    nwbfile_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    mode: str = "raw",
    stub_test: bool = False,
    append_on_disk_nwbfile: bool = False,
):
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    nwbfile_path: str or Path
        Path to the output NWB file.
    processed_data_dir_path: str or Path
        Path to the directory containing processed data.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    mode: str, default: "raw"
        Mode of conversion. Options are "raw" or "processed".
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).
    append_on_disk_nwbfile: bool, default: False
        If True, append data to an existing on-disk NWB file instead of creating a new one.

    """

    match mode:
        case "processed":
            nwbfile_path = convert_processed_session(
                nwbfile_path=nwbfile_path,
                processed_data_dir_path=processed_data_dir_path,
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                stub_test=stub_test,
                append_on_disk_nwbfile=append_on_disk_nwbfile,
            )


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Volumes/T9/data/IBL/zadorlab/Subjects/CSK-im-011/2021-07-13/001")
    processed_data_dir_path = data_dir_path / "alf/widefield"

    output_dir_path = Path("/Volumes/T9/data/IBL/nwbfiles")
    nwbfile_path = (
        output_dir_path / "/Volumes/T9/data/IBL/nwbfiles/84565bbe-fd4c-4bdb-af55-968d46a4c424-behav-processed.nwb"
    )
    append_on_disk_nwbfile = True  # Set to True to append to an existing NWB file

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = False  # Set to True for quick testing with limited data
    session_to_nwb(
        mode="processed",
        nwbfile_path=nwbfile_path,
        processed_data_dir_path=processed_data_dir_path,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
        append_on_disk_nwbfile=append_on_disk_nwbfile,
    )
