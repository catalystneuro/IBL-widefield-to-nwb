"""Primary NWBConverter class for this dataset."""

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv import BaseDataInterface, ConverterPipe
from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.utils import (
    get_ibl_subject_metadata,
    get_protocol_type_and_description,
    sanitize_subject_id_for_dandi,
)


class IblConverter(ConverterPipe):

    def __init__(
        self,
        one: ONE,
        session: str,
        data_interfaces: list[BaseDataInterface] | dict[str, BaseDataInterface],
        general_metadata_path: Path | None = None,
        verbose=False,
    ):
        self.one = one
        self.session = session
        # Dataset-specific general metadata (NWBFile keywords/description/experimenter + Subject
        # species/strain/description). Falls back to the generic placeholder if not provided.
        self._general_metadata_path = general_metadata_path or (
            Path(__file__).parent / "_metadata" / "widefield_general_metadata.yaml"
        )
        super().__init__(data_interfaces=data_interfaces, verbose=verbose)

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["additionalProperties"] = True
        metadata_schema["properties"]["Subject"]["additionalProperties"] = True

        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()  # Aggregates from the interfaces

        (session_metadata,) = self.one.alyx.rest(url="sessions", action="list", id=self.session)
        assert session_metadata["id"] == self.session, "Session metadata ID does not match the requested session ID."
        (lab_metadata,) = self.one.alyx.rest("labs", "list", name=session_metadata["lab"])

        session_start_time = datetime.fromisoformat(session_metadata["start_time"])
        tzinfo = ZoneInfo(lab_metadata["timezone"])
        session_start_time = session_start_time.replace(tzinfo=tzinfo)
        metadata["NWBFile"]["session_start_time"] = session_start_time
        metadata["NWBFile"]["session_id"] = session_metadata["id"]
        metadata["NWBFile"]["lab"] = session_metadata["lab"].replace("lab", "").capitalize()
        metadata["NWBFile"]["institution"] = lab_metadata["institution"]
        if session_metadata.get("task_protocol"):
            task_protocol = session_metadata["task_protocol"]
            metadata["NWBFile"]["protocol"] = task_protocol
            session_description = f"The task protocol(s) performed in this experimental session:\n"
            # Determine protocol type and description from the mapping
            protocols = task_protocol.split("/")  # In case there are multiple protocols listed, separated by /
            for i, protocol in enumerate(protocols):
                protocol_type, protocol_description = get_protocol_type_and_description(protocol)
                if protocol_type is not None:
                    session_description = session_description + f"{i+1}. {protocol_description}\n"
            metadata["NWBFile"]["session_description"] = session_description
        # Setting publication and experiment description at project-specific converter level
        subject_metadata_block = get_ibl_subject_metadata(
            one=self.one, session_metadata=session_metadata, tzinfo=tzinfo
        )
        subject_metadata_block["weight"] = str(subject_metadata_block["weight"])  # Ensure weight is a string
        subject_id = subject_metadata_block.get("subject_id", "unknown")
        # Sanitize subject nickname for DANDI compliance (replace underscores with hyphens)
        subject_metadata_block["subject_id"] = sanitize_subject_id_for_dandi(subject_id)
        metadata["Subject"].update(subject_metadata_block)

        return metadata


class WidefieldProcessedNWBConverter(IblConverter):
    """Primary conversion class for Widefield processed data."""

    def get_metadata(self):
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=self._general_metadata_path)
        metadata = dict_deep_update(metadata, experiment_metadata)

        # Ensure date_of_birth is a datetime object (Alyx returns it as an ISO string)
        dob = metadata.get("Subject", {}).get("date_of_birth")
        if isinstance(dob, str):
            parsed = datetime.fromisoformat(dob)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            metadata["Subject"]["date_of_birth"] = parsed

        return metadata


class WidefieldRawNWBConverter(IblConverter):
    """Primary conversion class for Widefield raw imaging data."""

    def get_metadata(self):
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=self._general_metadata_path)
        metadata = dict_deep_update(metadata, experiment_metadata)

        # Ensure date_of_birth is a datetime object (Alyx returns it as an ISO string)
        dob = metadata.get("Subject", {}).get("date_of_birth")
        if isinstance(dob, str):
            parsed = datetime.fromisoformat(dob)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            metadata["Subject"]["date_of_birth"] = parsed

        return metadata

    def temporally_align_data_interfaces(self, metadata: dict | None = None, conversion_options: dict | None = None):
        if "ImagingBlue" in self.data_interface_objects:
            functional_imaging_interface = self.data_interface_objects["ImagingBlue"]
            functional_imaging_interface.imaging_extractor.set_times(
                times=functional_imaging_interface.get_aligned_timestamps()
            )

        if "ImagingViolet" in self.data_interface_objects:
            isosbestic_imaging_interface = self.data_interface_objects["ImagingViolet"]
            isosbestic_imaging_interface.imaging_extractor.set_times(
                times=isosbestic_imaging_interface.get_aligned_timestamps()
            )
