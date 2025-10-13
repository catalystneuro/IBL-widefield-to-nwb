"""Primary NWBConverter class for this dataset."""
from neuroconv import NWBConverter

from src.ibl_widefield_to_nwb.widefield2025 import WidefieldSegmentationInterface, WidefieldImagingInterface


class Widefield2025NWBConverter(NWBConverter):
    """Primary conversion class for Widefield data."""

    data_interface_classes = dict(
        ImagingBlue=WidefieldImagingInterface,
        ImagingViolet=WidefieldImagingInterface,
        SegmentationBlue=WidefieldSegmentationInterface,
        SegmentationViolet=WidefieldSegmentationInterface,
    )
