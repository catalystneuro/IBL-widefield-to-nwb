"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter

from ibl_widefield_to_nwb.widefield2025.datainterfaces import (
    WidefieldSegmentationInterface,
)


class WidefieldProcessedNWBConverter(NWBConverter):
    """Primary conversion class for Widefield processed data."""

    data_interface_classes = dict(
        SegmentationBlue=WidefieldSegmentationInterface,
        SegmentationViolet=WidefieldSegmentationInterface,
    )
