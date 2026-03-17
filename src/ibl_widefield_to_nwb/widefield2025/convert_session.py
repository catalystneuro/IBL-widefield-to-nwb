"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path

from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.conversion import (
    convert_processed_session,
    convert_raw_session,
)


def session_to_nwb(
    one: ONE,
    eid: str,
    nwbfiles_folder_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    general_metadata_path: Path | None = None,
    mode: str = "raw",
    force_cache: bool = False,
    stub_test: bool = False,
):
    """
    Convert a single session of widefield data to NWB format.

    Data is downloaded lazily via the ONE API as needed. For raw mode, raw widefield files are
    explicitly downloaded before building the frame cache; all other data is fetched on demand.

    Parameters
    ----------
    one: ONE
        An instance of the ONE API to access data.
    eid: str
        The session ID.
    nwbfiles_folder_path: str or Path
        Path to the directory to save the output NWB file.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    general_metadata_path: Path, optional
        Path to the dataset-specific general metadata YAML (NWBFile + Subject fields).
        If None, falls back to the generic ``_metadata/widefield_general_metadata.yaml``.
        Use ``_metadata/widefield_general_metadata_CSK.yaml`` for the IBL BWM dataset
        and ``_metadata/widefield_general_metadata_FD.yaml`` for the Nrxn1α KO dataset.
    mode: str, default: "raw"
        Mode of conversion. Options are "raw" or "processed".
    force_cache: bool, default: False
        If True, force rebuilding of the frame cache even if it already exists (raw mode only).
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).
    """

    nwbfiles_folder_path = Path(nwbfiles_folder_path)
    nwbfiles_folder_path.mkdir(parents=True, exist_ok=True)

    match mode:
        case "raw":
            nwbfile_path = convert_raw_session(
                eid=eid,
                one=one,
                nwbfiles_folder_path=nwbfiles_folder_path,
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                general_metadata_path=general_metadata_path,
                force_cache=force_cache,
                stub_test=stub_test,
            )
        case "processed":
            nwbfile_path = convert_processed_session(
                eid=eid,
                one=one,
                nwbfiles_folder_path=nwbfiles_folder_path,
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                general_metadata_path=general_metadata_path,
                stub_test=stub_test,
            )
        case _:
            raise ValueError(f"Mode '{mode}' not recognized. Use 'raw' or 'processed'.")

    print(f"\n✓ NWB file created/updated successfully at: {nwbfile_path}")


if __name__ == "__main__":

    # Parameters for conversion
    output_dir_path = Path("/Volumes/T9/data/IBL/nwbfiles")

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = False  # Set to True for quick testing with limited data

    # ONE api instance
    from one.api import ONE

    one = ONE()
    # eid = "d34a502f-bd06-471f-8334-df41f785e1d9" error 404 for raw data
    eid = "2864dca1-38d8-464c-9777-f6fdfd5e63b5"

    mode = "processed"  # Choose between "raw" or "processed" mode

    session_to_nwb(
        one=one,
        eid=eid,
        nwbfiles_folder_path=output_dir_path,
        mode=mode,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
    )
