"""Primary NWBConverter class for this dataset."""

import json
from pathlib import Path
from warnings import warn

from neuroconv import BaseDataInterface, ConverterPipe, NWBConverter
from pydantic import DirectoryPath
from pynwb import NWBFile

from ibl_widefield_to_nwb.widefield2025.datainterfaces import (
    WidefieldSVDInterface,
)
from ibl_widefield_to_nwb.widefield2025.utils import (
    _apply_channel_name_mapping,
    _create_channel_name_mapping,
    _get_imaging_times_by_excitation_wavelength_nm,
)


class WidefieldProcessedNWBConverter(NWBConverter):
    """Primary conversion class for Widefield processed data."""

    data_interface_classes = dict(
        SVDCalcium=WidefieldSVDInterface,
        SVDIsosbestic=WidefieldSVDInterface,
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

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict | None = None, conversion_options: dict | None = None):
        if "NIDQ" not in self.data_interface_objects:
            return super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

        nidq_interface = self.data_interface_objects["NIDQ"]
        recording_extractor = nidq_interface.recording_extractor
        nidq_data_folder_path = nidq_interface.source_data["folder_path"]
        nidq_data_folder_path = Path(nidq_data_folder_path)
        wiring_file_name = "_spikeglx_ephysData_g0_t0.nidq.wiring.json"
        wiring_file_paths = list(nidq_data_folder_path.parent.rglob(wiring_file_name))

        if len(wiring_file_paths) != 1:
            warn(
                f"Expected exactly one wiring json file ('{wiring_file_name}'), found {len(wiring_file_paths)} files. "
                f"Not applying wiring analog channel filtering based on wiring."
            )
            return super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

        wiring_file_path = str(wiring_file_paths[0])
        wiring = json.load(open(wiring_file_path, "r"))

        channel_name_mapping = _create_channel_name_mapping(wiring=wiring)
        channel_names = recording_extractor.get_channel_ids()
        applied = _apply_channel_name_mapping(channel_names, channel_name_mapping)
        # Rename channels in the recording extractor
        recording_extractor.set_property(key="channel_names", values=applied)

        # Filter analog channel ids based on wiring json
        filtered_analog_channel_ids = [
            channel_id_from_wiring
            for channel_id_from_wiring in channel_name_mapping.keys()
            for analog_channel_id in nidq_interface.analog_channel_ids
            if str(analog_channel_id) in str(channel_id_from_wiring)
        ]
        nidq_interface.analog_channel_ids = filtered_analog_channel_ids

        return super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)
