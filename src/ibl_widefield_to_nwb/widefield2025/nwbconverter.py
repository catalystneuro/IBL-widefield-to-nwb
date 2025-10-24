"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter

from .ibl_widefield_segmentationinterface import WidefieldSegmentationInterface


class WidefieldProcessedNWBConverter(NWBConverter):
    """Primary conversion class for Widefield processed data."""

    data_interface_classes = dict(
        SegmentationBlue=WidefieldSegmentationInterface,
        SegmentationViolet=WidefieldSegmentationInterface,
    )
