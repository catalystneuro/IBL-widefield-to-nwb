"""Primary NWBConverter class for this dataset."""
from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    SpikeGLXRecordingInterface,
    PhySortingInterface,
)

from ibl_widefield_to_nwb.widefield2025 import Widefield2025BehaviorInterface


class Widefield2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    data_interface_classes = dict(
        Recording=SpikeGLXRecordingInterface,
        Sorting=PhySortingInterface,
        Behavior=Widefield2025BehaviorInterface,
    )
