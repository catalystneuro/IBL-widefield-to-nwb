from pathlib import Path
from warnings import warn

from ibl_to_nwb.datainterfaces._base_ibl_interface import BaseIBLDataInterface
from ibl_to_nwb.utils import decompress_ephys_cbins
from neuroconv.datainterfaces import SpikeGLXNIDQInterface
from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE

# =============================================================================
# Digital Device Labels (needed at init time for digital_channel_groups)
# These define how to interpret binary values (0/1) for each device type
# =============================================================================

DIGITAL_DEVICE_LABELS = {
    "left_camera": {0: "exposure_end", 1: "frame_start"},
    "right_camera": {0: "exposure_end", 1: "frame_start"},
    "body_camera": {0: "exposure_end", 1: "frame_start"},
    "imec_sync": {0: "sync_low", 1: "sync_high"},
    "frame_trigger": {0: "frame_off", 1: "frame_on"},
    "frame2ttl": {0: "screen_dark", 1: "screen_bright"},
    "rotary_encoder_0": {0: "phase_low", 1: "phase_high"},
    "rotary_encoder_1": {0: "phase_low", 1: "phase_high"},
    "audio": {0: "audio_off", 1: "audio_on"},
}


class IblNIDQInterface(SpikeGLXNIDQInterface, BaseIBLDataInterface):
    """IBL-specific NIDQ interface for widefield sessions with a Neuropixels NIDQ board.

    This interface wraps NeuroConv's ``SpikeGLXNIDQInterface`` and handles IBL-specific
    setup steps before delegating to the parent class:

    1. **Decompression**: the ``.cbin`` file is decompressed to a ``decompressed/``
       subfolder before SpikeGLX readers can open it.
    2. **Re-encoding**: some SpikeGLX ``.meta`` files contain Latin-1 bytes (e.g. the
       degree symbol) that cause UnicodeDecodeError in Neo. ``_reencode_meta_files_to_utf8``
       fixes them in-place.
    3. **Wiring-driven channel config**: ``wiring.json`` maps hardware ports (``P0.x``
       digital, ``AIx`` analog) to device names. The two ``get_*_channel_groups_from_wiring``
       static methods build the ``analog_channel_groups`` / ``digital_channel_groups`` dicts
       that the parent class needs. Adding a new device requires an entry in
       ``DIGITAL_DEVICE_LABELS`` above and a corresponding entry in
       ``_metadata/widefield_nidq_metadata.yaml``.

    This interface is the **preferred** sync source. ``IblWidefieldDAQInterface`` is used
    as a fallback when ``raw_ephys_data/`` is absent and ``raw_sync_data/`` is available.

    Example wiring.json structure::

        {
          "SYNC_WIRING_DIGITAL": {
            "P0.0": "left_camera",
            "P0.5": "rotary_encoder_0",
            "P0.7": "audio"
          },
          "SYNC_WIRING_ANALOG": {
            "AI0": "bpod"
          }
        }
    """

    COLLECTION = "raw_ephys_data"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Get data requirements for NIDQ interface.

        Returns
        -------
        dict
            Dictionary with required NIDQ files including wiring.json.
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.cbin",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.meta",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.ch",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json",
                ],
            },
        }

    def __init__(self, *, one: ONE, session: str, metadata_key: str = "SpikeGLXNIDQ"):

        session_path = one.eid2path(session)
        source_folder = session_path / self.COLLECTION
        target_folder = source_folder / "decompressed"
        decompress_ephys_cbins(source_folder=source_folder, target_folder=target_folder)
        self._reencode_meta_files_to_utf8(target_folder)

        self.wiring = one.load_dataset(
            session,
            dataset="_spikeglx_ephysData_g0_t0.nidq.wiring.json",
            collection=self.COLLECTION,
        )
        analog_channel_groups = self.get_analog_channel_groups_from_wiring(wiring=self.wiring)
        digital_channel_groups = self.get_digital_channel_groups_from_wiring(wiring=self.wiring)

        super().__init__(
            folder_path=target_folder,
            analog_channel_groups=analog_channel_groups,
            digital_channel_groups=digital_channel_groups,
            metadata_key=metadata_key,
        )

    @staticmethod
    def _reencode_meta_files_to_utf8(folder: Path) -> None:
        """Re-encode any .meta files in folder from latin-1 to UTF-8 in-place.

        Some SpikeGLX .meta files contain non-UTF-8 bytes (e.g. the degree symbol
        0xb0 in Latin-1). Neo reads them as UTF-8 and raises a UnicodeDecodeError.
        This method re-encodes such files so Neo can parse them correctly.
        """
        for meta_file in folder.glob("*.meta"):
            content = meta_file.read_bytes()
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                meta_file.write_text(content.decode("latin-1"), encoding="utf-8")

    def get_metadata(self):
        metadata = super().get_metadata()

        nidq_metadata_file_path = Path(__file__).parent.parent / "_metadata" / "widefield_nidq_metadata.yaml"
        nidq_device_metadata = load_dict_from_file(file_path=nidq_metadata_file_path)

        # Initialize metadata structure
        nidq_metadata = {"TimeSeries": {self.metadata_key: {}}, "Events": {self.metadata_key: {}}}

        # Map analog signals (TimeSeries)
        analog_signals_metadata = nidq_device_metadata.get("TimeSeries", {})
        analog_channel_groups = self.get_analog_channel_groups_from_wiring(wiring=self.wiring)
        for device_name in analog_channel_groups:
            if device_name in analog_signals_metadata:
                nidq_metadata["TimeSeries"][self.metadata_key][device_name] = analog_signals_metadata[device_name]

        # Map digital signals (Events)
        digital_signals_metadata = nidq_device_metadata.get("Events", {})
        digital_channel_groups = self.get_digital_channel_groups_from_wiring(wiring=self.wiring)
        for device_name in digital_channel_groups:
            if device_name in digital_signals_metadata:
                nidq_metadata["Events"][self.metadata_key][device_name] = digital_signals_metadata[device_name]

        metadata = dict_deep_update(metadata, nidq_metadata)

        return metadata

    @staticmethod
    def get_analog_channel_groups_from_wiring(wiring: dict[str, str]) -> dict[str, dict]:
        """
        Get analog channel groups from wiring configuration.


        Parameters
        ----------
        wiring: dict[str, str]
            Wiring configuration from `_spikeglx_ephysData_g0_t0.nidq.wiring.json` file loaded as a dictionary.

        Returns
        -------
        dict[str, list[str]]
            Mapping from device names to lists of SpikeGLX analog channel IDs that are specified in the wiring configuration.
            Example: {"bpod": {"channels": ["nidq#XA0"]}}

        """
        analog_channel_groups = {}

        analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})
        for analog_input, device_name in analog_wiring.items():
            if analog_input.startswith("AI"):
                channel_num = analog_input[2:]
                channel_id = f"nidq#XA{channel_num}"
                analog_channel_groups[device_name] = {"channels": [channel_id]}

        return analog_channel_groups

    @staticmethod
    def get_digital_channel_groups_from_wiring(wiring: dict[str, str]) -> dict[str, dict]:
        """
        Get digital channel groups from wiring configuration.

        Parameters
        ----------
        wiring: dict[str, str]
            Wiring configuration from `_spikeglx_ephysData_g0_t0.nidq.wiring.json` file loaded as a dictionary.

        Returns
        -------
        dict[str, list[str]]
            Mapping from device names to lists of SpikeGLX digital channel IDs that are specified in the wiring configuration.
            Example: {"left_camera": {"channels": ["nidq#XD0"]}}

        """
        digital_channel_groups = {}

        digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})
        for port_pin, device_name in digital_wiring.items():
            if port_pin.startswith("P0."):
                bit_num = port_pin.split(".")[-1]
                channel_id = f"nidq#XD{bit_num}"

                if device_name in DIGITAL_DEVICE_LABELS:
                    digital_channel_groups[device_name] = {
                        "channels": {channel_id: {"labels_map": DIGITAL_DEVICE_LABELS[device_name]}}
                    }
                else:
                    warn(
                        f"No labels configured for digital device '{device_name}' "
                        f"at channel {channel_id} (port {port_pin}). ",
                        UserWarning,
                        stacklevel=2,
                    )

        return digital_channel_groups
