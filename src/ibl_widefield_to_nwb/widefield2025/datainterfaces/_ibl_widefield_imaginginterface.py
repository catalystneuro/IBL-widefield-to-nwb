from copy import deepcopy
from pathlib import Path
from typing import Literal

from neuroconv.datainterfaces.ophys.baseimagingextractorinterface import (
    BaseImagingExtractorInterface,
)
from neuroconv.utils import DeepDict, dict_deep_update, load_dict_from_file
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.datainterfaces._base_ibl_interface import (
    BaseIBLDataInterface,
)
from ibl_widefield_to_nwb.widefield2025.datainterfaces._ibl_widefield_imagingextractor import (
    TRANSPOSE_OUTPUT,
    WidefieldImagingExtractor,
)


class WidefieldImagingInterface(BaseImagingExtractorInterface, BaseIBLDataInterface):
    """Data Interface for WidefieldImagingExtractor."""

    display_name = "IBL Widefield Imaging"
    associated_suffixes = (".mov", ".htsv", ".camlog")
    info = "Interface for IBL Widefield imaging data."

    @classmethod
    def get_extractor_class(cls):
        return WidefieldImagingExtractor

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for raw Widefield data.

        Returns
        -------
        dict
            Data requirements specification with exact file paths
        """
        return {
            "one_objects": [],  # Uses load_dataset directly, not load_object
            "exact_files_options": {
                "standard": [
                    "raw_widefield_data/imaging.frames.mov",
                    "raw_widefield_data/widefieldChannels.wiring.htsv",
                    "raw_widefield_data/widefieldEvents.raw.camlog",
                    # For aligned timestamps
                    "alf/widefield/imaging.times.npy",
                    "alf/widefield/imaging.imagingLightSource.npy",
                ]
            },
        }

    def __init__(
        self,
        folder_path: DirectoryPath,
        cache_folder_path: DirectoryPath,
        excitation_wavelength_nm: int | None = None,
        photon_series_type: Literal["OnePhotonSeries", "TwoPhotonSeries"] = "OnePhotonSeries",
        verbose: bool = False,
    ):

        folder_path = Path(folder_path)
        cache_folder_path = Path(cache_folder_path)

        cached_movie_file_path = cache_folder_path / "frames.dat"
        if not cached_movie_file_path.exists():
            raise FileNotFoundError(
                f"'frames.dat' not found in folder: {cache_folder_path}. Please build frame cache first."
            )

        htsv_file_paths = list(folder_path.glob("*.htsv"))
        if len(htsv_file_paths) == 0:
            raise FileNotFoundError(f"No .htsv files found in folder: {folder_path}")
        elif len(htsv_file_paths) > 1:
            raise ValueError(
                f"Multiple .htsv files found in folder: {folder_path}. Please ensure only one file is present."
            )
        htsv_file_path = str(htsv_file_paths[0])

        camlog_file_paths = list(folder_path.glob("*.camlog"))
        if len(camlog_file_paths) == 0:
            raise FileNotFoundError(f"No .camlog files found in folder: {folder_path}")
        elif len(camlog_file_paths) > 1:
            raise ValueError(
                f"Multiple .camlog files found in folder: {folder_path}. Please ensure only one file is present."
            )
        camlog_file_path = str(camlog_file_paths[0])

        super().__init__(
            folder_path=cache_folder_path,
            htsv_file_path=htsv_file_path,
            camlog_file_path=camlog_file_path,
            excitation_wavelength_nm=excitation_wavelength_nm,
            photon_series_type=photon_series_type,
            verbose=verbose,
        )

    def get_metadata(self) -> DeepDict:
        """
        Get metadata for the Widefield raw imaging.

        Returns
        -------
        DeepDict
            Dictionary containing metadata including device information, imaging plane details,
            and one-photon series configuration.
        """
        metadata = super().get_metadata()
        metadata_copy = deepcopy(metadata)

        # Use single source of truth when updating metadata
        ophys_metadata = load_dict_from_file(
            file_path=Path(__file__).parent.parent / "_metadata" / "widefield_ophys_metadata.yaml"
        )

        excitation_wavelength = float(self.source_data["excitation_wavelength_nm"])
        imaging_plane_metadata = next(
            (
                imaging_plane_meta
                for imaging_plane_meta in ophys_metadata["Ophys"]["ImagingPlane"]
                if imaging_plane_meta.get("excitation_lambda") == excitation_wavelength
            ),
            None,
        )
        if imaging_plane_metadata is None:
            raise ValueError(
                f"No 'ImagingPlane' metadata found for excitation wavelength: {excitation_wavelength} nm. "
            )
        imaging_plane_metadata.update(
            imaging_rate=float(self.imaging_extractor.get_sampling_frequency()),
        )
        imaging_plane_name = imaging_plane_metadata["name"]
        one_photon_series_metadata = next(
            (
                photon_series_meta
                for photon_series_meta in ophys_metadata["Ophys"]["OnePhotonSeries"]
                if photon_series_meta.get("imaging_plane") == imaging_plane_name
            ),
            None,
        )
        if one_photon_series_metadata is None:
            raise ValueError(f"No 'OnePhotonSeries' metadata found for imaging plane: {imaging_plane_name}. ")

        # TODO: remove once neuroconv supports (height, width) format
        if TRANSPOSE_OUTPUT:
            # Transpose it back to height x width (now it matches the series shape)
            one_photon_series_metadata["dimension"] = self.imaging_extractor.get_sample_shape()[::-1]

        metadata_copy["Ophys"]["Device"] = ophys_metadata["Ophys"]["Device"]
        metadata_copy["Ophys"]["ImagingPlane"][0] = dict_deep_update(
            metadata_copy["Ophys"]["ImagingPlane"][0], imaging_plane_metadata
        )
        metadata_copy["Ophys"]["OnePhotonSeries"][0] = dict_deep_update(
            metadata_copy["Ophys"]["OnePhotonSeries"][0], one_photon_series_metadata
        )

        return metadata_copy
