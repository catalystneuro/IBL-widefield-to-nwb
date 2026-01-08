"""Primary NWBConverter class for this dataset."""

from datetime import datetime

from neuroconv import BaseDataInterface, ConverterPipe
from one.api import ONE
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.utils import (
    _get_imaging_times_by_excitation_wavelength_nm,
)


class WidefieldProcessedNWBConverter(ConverterPipe):
    """Primary conversion class for Widefield processed data."""

    def __init__(
        self,
        one: ONE,
        eid: str,
        data_interfaces: list[BaseDataInterface] | dict[str, BaseDataInterface],
        verbose=False,
    ):
        self.one = one
        self.eid = eid
        super().__init__(data_interfaces=data_interfaces, verbose=verbose)

    def get_metadata(self):
        metadata = super().get_metadata()

        try:
            ((session_metadata),) = self.one.alyx.rest(url="sessions", action="list", id=self.eid)
        except Exception as e:
            raise RuntimeError(f"Failed to access ONE for eid {self.eid}: {e}")

        session_start_time = datetime.fromisoformat(session_metadata["start_time"])
        metadata["NWBFile"]["session_start_time"] = session_start_time
        metadata["NWBFile"]["session_id"] = self.eid
        metadata["Subject"]["subject_id"] = session_metadata["subject"]

        return metadata


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
