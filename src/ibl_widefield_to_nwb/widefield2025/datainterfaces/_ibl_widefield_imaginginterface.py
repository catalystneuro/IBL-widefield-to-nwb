from copy import deepcopy
from pathlib import Path
from typing import Literal

from neuroconv.datainterfaces.ophys.baseimagingextractorinterface import (
    BaseImagingExtractorInterface,
)
from neuroconv.utils import DeepDict
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.datainterfaces._ibl_widefield_imagingextractor import (
    WidefieldImagingExtractor,
)


class WidefieldImagingInterface(BaseImagingExtractorInterface):
    """Data Interface for WidefieldImagingExtractor."""

    display_name = "IBL Widefield Imaging"
    associated_suffixes = (".mov", ".htsv", ".camlog")
    info = "Interface for IBL Widefield imaging data."

    @classmethod
    def get_extractor_class(cls):
        return WidefieldImagingExtractor

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
        Get metadata for the Miniscope imaging data.

        Returns
        -------
        DeepDict
            Dictionary containing metadata including device information, imaging plane details,
            and one-photon series configuration.
        """
        metadata = super().get_metadata()
        metadata_copy = deepcopy(metadata)  # To avoid modifying the parent class's metadata
        imaging_plane_metadata = metadata_copy["Ophys"]["ImagingPlane"][0]

        excitation_wavelength = float(self.source_data["excitation_wavelength_nm"])
        suffix = "calcium" if excitation_wavelength == 470.0 else "isosbestic"
        imaging_plane_metadata.update(
            name=f"imaging_plane_{suffix}",
            excitation_lambda=excitation_wavelength,
            imaging_rate=self.imaging_extractor.get_sampling_frequency(),
        )

        one_photon_series_metadata = metadata_copy["Ophys"]["OnePhotonSeries"][0]
        one_photon_series_metadata.update(
            name=f"one_photon_series_{suffix}",
            imaging_plane=imaging_plane_metadata["name"],
            unit="px",
        )

        return metadata_copy
