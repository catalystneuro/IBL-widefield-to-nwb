"""Primary NWBConverter class for this dataset."""

from neuroconv import BaseDataInterface, ConverterPipe
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.utils import (
    _get_imaging_times_by_excitation_wavelength_nm,
)


class WidefieldRawNWBConverter(ConverterPipe):
    """Primary conversion class for Widefield imaging data."""

    FUNCTIONAL_WAVELENGTH_NM = 470
    ISOSBESTIC_WAVELENGTH_NM = 405

    def __init__(
        self,
        data_interfaces: list[BaseDataInterface] | dict[str, BaseDataInterface],
        processed_data_folder_path: DirectoryPath | None = None,
        verbose=False,
    ):
        if processed_data_folder_path is not None:
            self._aligned_times_file_path = processed_data_folder_path / "imaging.times.npy"
            self._light_source_file_path = processed_data_folder_path / "imaging.imagingLightSource.npy"
            self._light_source_properties_file_path = processed_data_folder_path / "imagingLightSource.properties.htsv"

        super().__init__(data_interfaces=data_interfaces, verbose=verbose)

    def temporally_align_data_interfaces(self, metadata: dict | None = None, conversion_options: dict | None = None):
        if "ImagingBlue" in self.data_interface_objects:
            functional_imaging_interface = self.data_interface_objects["ImagingBlue"]

            functional_imaging_times = _get_imaging_times_by_excitation_wavelength_nm(
                excitation_wavelength_nm=self.FUNCTIONAL_WAVELENGTH_NM,
                aligned_times_file_path=self._aligned_times_file_path,
                light_source_file_path=self._light_source_file_path,
                light_source_properties_file_path=self._light_source_properties_file_path,
            )
            functional_imaging_interface.imaging_extractor.set_times(times=functional_imaging_times)

        if "ImagingViolet" in self.data_interface_objects:
            isosbestic_imaging_interface = self.data_interface_objects["ImagingViolet"]
            isosbestic_imaging_times = _get_imaging_times_by_excitation_wavelength_nm(
                excitation_wavelength_nm=self.ISOSBESTIC_WAVELENGTH_NM,
                aligned_times_file_path=self._aligned_times_file_path,
                light_source_file_path=self._light_source_file_path,
                light_source_properties_file_path=self._light_source_properties_file_path,
            )
            isosbestic_imaging_interface.imaging_extractor.set_times(times=isosbestic_imaging_times)
