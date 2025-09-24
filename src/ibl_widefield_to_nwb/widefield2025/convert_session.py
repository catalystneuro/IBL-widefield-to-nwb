"""Primary script to run to convert an entire session for of data using the NWBConverter."""
from pathlib import Path
from typing import Union
import datetime
from zoneinfo import ZoneInfo

from neuroconv.utils import load_dict_from_file, dict_deep_update

from ibl_widefield_to_nwb.widefield2025 import Widefield2025NWBConverter


def session_to_nwb(data_dir_path: Union[str, Path], output_dir_path: Union[str, Path], stub_test: bool = False):

    data_dir_path = Path(data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    session_id = "subject_identifier_usually"
    nwbfile_path = output_dir_path / f"{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # Add Recording
    source_data.update(dict(Recording=dict()))
    conversion_options.update(dict(Recording=dict(stub_test=stub_test)))

    # Add Sorting
    source_data.update(dict(Sorting=dict()))
    conversion_options.update(dict(Sorting=dict()))

    # Add Behavior
    source_data.update(dict(Behavior=dict()))
    conversion_options.update(dict(Behavior=dict()))

    converter = Widefield2025NWBConverter(source_data=source_data)

    # Add datetime to conversion
    metadata = converter.get_metadata()
    date = datetime.datetime(year=2020, month=1, day=1, tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = date

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent / "widefield2025_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # Run conversion
    converter.run_conversion(metadata=metadata, nwbfile_path=nwbfile_path, conversion_options=conversion_options)


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Directory/With/Raw/Formats/")
    output_dir_path = Path("~/conversion_nwb/")
    stub_test = False

<<<<<<< HEAD:IBL-widefield-to-nwb/src/ibl_widefield_to_nwb/widefield2025/convert_session.py
    session_to_nwb(data_dir_path=data_dir_path, output_dir_path=output_dir_path, stub_test=stub_test)
=======
    session_to_nwb(data_dir_path=data_dir_path,
                    output_dir_path=output_dir_path,
                    stub_test=stub_test,
                    )
>>>>>>> main:IBL-widefield-to-nwb/src/ibl_widefield_to_nwb/widefield2025/widefield2025_convert_session.py
