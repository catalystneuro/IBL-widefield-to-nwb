import warnings
from pathlib import Path

import numpy as np
from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE
from pynwb import NWBFile
from pynwb.base import TimeSeries

from ibl_widefield_to_nwb.widefield2025.datainterfaces._base_ibl_interface import (
    BaseIBLDataInterface,
)

# =============================================================================
# Digital Device Labels
# These define how to interpret polarity values (0/1) for each device type
# in the widefield DAQ wiring configuration.
# =============================================================================

DIGITAL_DEVICE_LABELS = {
    "left_camera": {0: "exposure_end", 1: "frame_start"},
    "right_camera": {0: "exposure_end", 1: "frame_start"},
    "body_camera": {0: "exposure_end", 1: "frame_start"},
    "frame_trigger": {0: "frame_off", 1: "frame_on"},
    "frame2ttl": {0: "screen_dark", 1: "screen_bright"},
    "rotary_encoder_0": {0: "phase_low", 1: "phase_high"},
    "rotary_encoder_1": {0: "phase_low", 1: "phase_high"},
    "audio": {0: "audio_off", 1: "audio_on"},
    "bpod": {0: "ttl_low", 1: "ttl_high"},
}


class IblWidefieldDAQInterface(BaseIBLDataInterface):
    """
    IBL-specific DAQ interface for widefield sessions.

    This interface handles DAQ data recorded by the SpikeGLX DAQ board during widefield
    imaging sessions. The data lives in the `raw_sync_data` collection and includes:

    - Pre-extracted digital sync events (_spikeglx_sync.{channels,polarities,times}.npy)
    - Raw DAQ recording (_spikeglx_DAQdata.raw.{cbin,meta,ch}) for analog channels
    - Wiring configuration (_spikeglx_DAQdata.wiring.json) mapping ports to devices

    Digital channels are loaded from the pre-extracted sync files. Analog channels
    are read from the raw .cbin file using spikeglx.Reader.

    Example wiring.json structure:
    {
        "SYSTEM": "Widefield",
        "SYNC_WIRING_DIGITAL": {
            "P0.0": "left_camera",
            "P0.1": "right_camera",
            "P0.2": "body_camera",
            "P0.3": "frame_trigger",
            "P0.4": "frame2ttl",
            "P0.5": "rotary_encoder_0",
            "P0.6": "rotary_encoder_1",
            "P0.7": "audio"
        },
        "SYNC_WIRING_ANALOG": {
            "AI0": "bpod",
            "AI1": "laser",
            "AI2": "laser_ttl"
        }
    }
    """

    display_name = "Widefield DAQ"
    info = "Interface for widefield DAQ board recording data."
    interface_name = "IblWidefieldDAQInterface"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Get data requirements for the widefield DAQ interface.

        Returns
        -------
        dict
            Dictionary with required DAQ files. The "standard" option includes
            both the pre-extracted sync files (for digital events) and the raw
            .cbin files (for analog channels).
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    "raw_sync_data/_spikeglx_DAQdata.wiring.json",
                    "raw_sync_data/_spikeglx_DAQdata.raw.cbin",
                    "raw_sync_data/_spikeglx_DAQdata.raw.meta",
                    "raw_sync_data/_spikeglx_DAQdata.raw.ch",
                    "raw_sync_data/_spikeglx_sync.channels.npy",
                    "raw_sync_data/_spikeglx_sync.polarities.npy",
                    "raw_sync_data/_spikeglx_sync.times.npy",
                ],
            },
        }

    def __init__(self, one: ONE, session: str, metadata_key: str = "IblDAQ"):
        """
        Initialize the IblWidefieldDAQInterface.

        Parameters
        ----------
        one : ONE
            An instance of the ONE API.
        session : str
            The session ID (eid).
        metadata_key : str, default: "IblDAQ"
            Key used to organize TimeSeries and Events metadata.
        """
        super().__init__(one=one, session=session)
        self.one = one
        self.session = session
        self.metadata_key = metadata_key

        # Load wiring configuration
        self.wiring = self.one.load_dataset(
            self.session,
            dataset="_spikeglx_DAQdata.wiring.json",
            collection="raw_sync_data",
        )

        # Build channel groups from wiring
        self._digital_channel_groups = self.get_digital_channel_groups_from_wiring(self.wiring)
        self._analog_channel_groups = self.get_analog_channel_groups_from_wiring(self.wiring)

        self.has_digital_channels = len(self._digital_channel_groups) > 0
        self.has_analog_channels = len(self._analog_channel_groups) > 0

    @staticmethod
    def get_digital_channel_groups_from_wiring(wiring: dict) -> dict:
        """
        Build digital channel groups from wiring configuration.

        Maps each digital device in the wiring to its channel index (from the P0.x port)
        and labels_map (from DIGITAL_DEVICE_LABELS).

        Parameters
        ----------
        wiring : dict
            Wiring configuration loaded from _spikeglx_DAQdata.wiring.json.

        Returns
        -------
        dict
            digital_channel_groups structure.
            Example: {
                "left_camera": {
                    "channel_index": 0,
                    "labels_map": {0: "exposure_end", 1: "frame_start"}
                }
            }
        """
        digital_channel_groups = {}
        digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})

        for port_pin, device_name in digital_wiring.items():
            if port_pin.startswith("P0."):
                channel_index = int(port_pin.split(".")[-1])

                if device_name in DIGITAL_DEVICE_LABELS:
                    digital_channel_groups[device_name] = {
                        "channel_index": channel_index,
                        "labels_map": DIGITAL_DEVICE_LABELS[device_name],
                    }
                else:
                    warnings.warn(
                        f"No labels configured for digital device '{device_name}' "
                        f"at port {port_pin} (channel index {channel_index}). "
                        f"Add an entry to DIGITAL_DEVICE_LABELS in _ibl_widefield_DAQ_interface.py.",
                        UserWarning,
                        stacklevel=2,
                    )

        return digital_channel_groups

    @staticmethod
    def get_analog_channel_groups_from_wiring(wiring: dict) -> dict:
        """
        Build analog channel groups from wiring configuration.

        Maps each analog device in the wiring to its channel index (from the AIx port).
        Excludes devices that are already handled as digital channels.

        Parameters
        ----------
        wiring : dict
            Wiring configuration loaded from _spikeglx_DAQdata.wiring.json.

        Returns
        -------
        dict
            analog_channel_groups structure.
            Example: {"bpod": {"channel_index": 0}}
        """
        analog_channel_groups = {}
        analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})

        for analog_input, device_name in analog_wiring.items():
            if analog_input.startswith("AI"):
                channel_index = int(analog_input[2:])
                analog_channel_groups[device_name] = {"channel_index": channel_index}

        return analog_channel_groups

    def get_metadata(self):
        """
        Get metadata with IBL-specific channel configurations.

        Loads static metadata from widefield_DAQ_metadata.yaml and filters to only
        include devices present in this session's wiring.json.

        Returns
        -------
        dict
            Metadata dictionary with:
            - Events metadata for digital channels (name, description, meanings)
            - TimeSeries metadata for analog channels (name, description)
        """
        metadata = super().get_metadata()

        # Load static metadata from YAML
        static_metadata = load_dict_from_file(
            file_path=Path(__file__).parent.parent / "_metadata" / "widefield_DAQ_metadata.yaml"
        )

        # Get devices present in this session's wiring
        analog_devices = set(self.wiring.get("SYNC_WIRING_ANALOG", {}).values())
        digital_devices = set(self.wiring.get("SYNC_WIRING_DIGITAL", {}).values())

        # Filter TimeSeries metadata to only include analog devices in wiring
        timeseries_metadata = {}
        for device in analog_devices:
            if device in static_metadata.get("TimeSeries", {}):
                timeseries_metadata[device] = static_metadata["TimeSeries"][device].copy()
            else:
                warnings.warn(
                    f"No metadata configured for analog device '{device}'. "
                    f"Add an entry to _metadata/widefield_DAQ_metadata.yaml.",
                    UserWarning,
                    stacklevel=2,
                )

        if timeseries_metadata:
            metadata = dict_deep_update(metadata, {"TimeSeries": {self.metadata_key: timeseries_metadata}})

        # Filter Events metadata to only include digital devices in wiring
        events_metadata = {}
        for device in digital_devices:
            if device in static_metadata.get("Events", {}):
                events_metadata[device] = static_metadata["Events"][device].copy()
            else:
                warnings.warn(
                    f"No metadata configured for digital device '{device}'. "
                    f"Add an entry to _metadata/widefield_DAQ_metadata.yaml.",
                    UserWarning,
                    stacklevel=2,
                )

        if events_metadata:
            metadata = dict_deep_update(metadata, {"Events": {self.metadata_key: events_metadata}})

        return metadata

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict | None = None,
        *,
        stub_test: bool = False,
    ):
        """
        Add DAQ board data to an NWB file, including both analog and digital channels.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the DAQ data will be added.
        metadata : dict | None, default: None
            Metadata dictionary with device information. If None, uses default metadata.
        stub_test : bool, default: False
            If True, only writes a small amount of data for testing.
        """
        metadata = metadata or self.get_metadata()

        sync_data = None
        if self.has_digital_channels or self.has_analog_channels:
            # Load pre-extracted sync data (needed for digital events and analog starting_time)
            sync_data = self.one.load_object(
                self.session,
                "sync",
                collection="raw_sync_data",
            )

        if self.has_digital_channels:
            self._add_digital_channels(nwbfile=nwbfile, metadata=metadata, sync_data=sync_data)

        if self.has_analog_channels:
            self._add_analog_channels(nwbfile=nwbfile, metadata=metadata, stub_test=stub_test, sync_data=sync_data)

    def _add_digital_channels(
        self,
        nwbfile: NWBFile,
        metadata: dict,
        sync_data: dict,
    ):
        """
        Add digital channels from the DAQ board to the NWB file as LabeledEvents.

        Uses the pre-extracted sync data (_spikeglx_sync.{channels,polarities,times}.npy)
        to create event objects for each digital device.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the digital channels to.
        metadata : dict
            Metadata dictionary containing Events configurations.
        sync_data : dict
            Pre-extracted sync data with keys "channels", "polarities", "times".
        """
        from ndx_events import LabeledEvents

        events_metadata = metadata.get("Events", {}).get(self.metadata_key, {})

        channels = sync_data["channels"]
        polarities = sync_data["polarities"]
        times = sync_data["times"]

        for device_name, group_config in self._digital_channel_groups.items():
            channel_index = group_config["channel_index"]
            labels_map = group_config["labels_map"]

            # Filter sync events for this channel
            mask = channels == channel_index
            device_times = times[mask]
            device_polarities = polarities[mask]

            if device_times.size == 0:
                continue

            # Convert polarities from (-1, 1) to (0, 1) for indexing into labels
            data = (device_polarities == 1).astype(int)

            # Get NWB properties from metadata
            device_meta = events_metadata.get(device_name, {})
            name = device_meta.get("name", f"Events{device_name.replace('_', ' ').title().replace(' ', '')}")
            description = device_meta.get("description", f"Digital events for {device_name}")

            # Append meanings to description if provided
            meanings = device_meta.get("meanings", {})
            if meanings:
                meanings_text = "\n".join(f"  - {label}: {meaning}" for label, meaning in meanings.items())
                description = f"{description}\n\nLabel meanings:\n{meanings_text}"

            # Build labels list from labels_map
            sorted_items = sorted(labels_map.items())
            labels_list = [label for _, label in sorted_items]

            labeled_events = LabeledEvents(
                name=name,
                description=description,
                timestamps=device_times,
                data=data,
                labels=labels_list,
            )
            nwbfile.add_acquisition(labeled_events)

    @staticmethod
    def _parse_analog_channel_names(meta: dict) -> dict[str, int]:
        """
        Parse the analogChannelNames field from SpikeGLX meta to build a
        mapping from device name to column index in the raw data.

        The meta field has format: "(ai0,bpod)(ai1,laser)" etc.
        The column index is the position in the list (offset by MN+MA channels).

        Parameters
        ----------
        meta : dict
            SpikeGLX metadata dictionary from spikeglx.Reader.meta.

        Returns
        -------
        dict[str, int]
            Mapping from device name to column index in the raw data.
        """
        import re

        channel_names_str = meta.get("analogChannelNames", "")
        if not channel_names_str:
            return {}

        # Parse entries like "(ai0,bpod)(ai1,laser)"
        entries = re.findall(r"\(([^,]+),([^)]+)\)", channel_names_str)

        # snsMnMaXaDw gives [MN, MA, XA, XD] channel counts
        mn_ma_xa_dw = meta.get("snsMnMaXaDw", [0, 0, 0, 0])
        offset = int(mn_ma_xa_dw[0]) + int(mn_ma_xa_dw[1])  # MN + MA

        device_to_column = {}
        for i, (_, device_name) in enumerate(entries):
            device_to_column[device_name] = offset + i

        return device_to_column

    @staticmethod
    def _get_sync_channel_index_from_meta(meta: dict) -> int | None:
        """
        Determine the sync channel index used in ``_spikeglx_sync.channels.npy``
        from the SpikeGLX meta file fields ``syncNiChanType`` and ``syncNiChan``.

        SpikeGLX convention (from ``spikeglx._sync_map_from_hardware_config``):
        - Digital channels (P0.x): channel index = x  (bit in the 16-bit digital word)
        - Analog  channels (AIx):  channel index = x + 16

        ``syncNiChanType`` encodes the channel type:
        - 0: no sync
        - 1: digital (XD) – ``syncNiChan`` is the bit position in the digital word
        - 2: analog  (XA) – ``syncNiChan`` is the AI channel number; offset by 16

        Parameters
        ----------
        meta : dict
            SpikeGLX metadata dictionary from ``spikeglx.Reader.meta``.

        Returns
        -------
        int | None
            Channel index within the pre-extracted sync data, or ``None`` if the
            meta file does not contain sync channel information.
        """
        chan_type = meta.get("syncNiChanType")
        chan_num = meta.get("syncNiChan")
        if chan_type is None or chan_num is None:
            return None
        chan_type, chan_num = int(chan_type), int(chan_num)
        if chan_type == 1:  # digital
            return chan_num
        elif chan_type == 2:  # analog (offset by 16 per SpikeGLX convention)
            return chan_num + 16
        return None  # chan_type == 0: no sync configured

    def _add_analog_channels(
        self,
        nwbfile: NWBFile,
        metadata: dict,
        stub_test: bool = False,
        sync_data: dict | None = None,
    ):
        """
        Add analog channels from the DAQ board to the NWB file as TimeSeries.

        Reads the raw .cbin file using spikeglx.Reader and extracts each analog
        channel as a continuous voltage TimeSeries. Only channels that are actually
        present in the raw data (per the meta file's analogChannelNames) are processed.

        The ``starting_time`` for each TimeSeries is derived from the first event on the
        SpikeGLX sync channel, whose index is read dynamically from the meta file fields
        ``syncNiChanType`` and ``syncNiChan``. Falls back to ``0.0`` if the sync channel
        cannot be determined or has no events.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the analog channels to.
        metadata : dict
            Metadata dictionary with TimeSeries information.
        stub_test : bool, default: False
            If True, only reads a small portion of data for testing.
        sync_data : dict | None, default: None
            Pre-extracted sync data with keys ``"channels"``, ``"polarities"``, ``"times"``.
            Used to compute ``starting_time`` from the first event on the sync channel.
        """
        import spikeglx

        timeseries_metadata = metadata.get("TimeSeries", {}).get(self.metadata_key, {})

        # Download and open the raw .cbin file
        cbin_path = self.one.load_dataset(
            self.session,
            dataset="_spikeglx_DAQdata.raw.cbin",
            collection="raw_sync_data",
            download_only=True,
        )
        sr = spikeglx.Reader(cbin_path)

        try:
            # Compute starting_time from the first event on the SpikeGLX sync channel.
            # The sync channel index is read from the meta file (syncNiChanType / syncNiChan)
            # so the offset works correctly across different hardware configurations.
            starting_time = 0.0
            if sync_data is not None:
                sync_channel_index = self._get_sync_channel_index_from_meta(sr.meta)
                if sync_channel_index is not None:
                    mask = sync_data["channels"] == sync_channel_index
                    if np.any(mask):
                        starting_time = float(sync_data["times"][mask][0])
                    else:
                        warnings.warn(
                            f"No events found on sync channel {sync_channel_index} "
                            f"(syncNiChanType={sr.meta.get('syncNiChanType')}, "
                            f"syncNiChan={sr.meta.get('syncNiChan')}). "
                            "Analog TimeSeries starting_time defaults to 0.0.",
                            UserWarning,
                            stacklevel=2,
                        )
                else:
                    warnings.warn(
                        "syncNiChanType / syncNiChan not found in meta file. "
                        "Analog TimeSeries starting_time defaults to 0.0.",
                        UserWarning,
                        stacklevel=2,
                    )

            # Build mapping from device name to actual column index in raw data
            device_to_column = self._parse_analog_channel_names(sr.meta)

            n_samples = sr.ns
            if stub_test:
                n_samples = min(10000, n_samples)

            for device_name in self._analog_channel_groups:
                # Skip devices not actually recorded in the raw data
                if device_name not in device_to_column:
                    warnings.warn(
                        f"Analog device '{device_name}' is in wiring.json but not in "
                        f"the raw data (analogChannelNames). Skipping.",
                        UserWarning,
                        stacklevel=2,
                    )
                    continue

                # Check if this device has metadata configured
                if device_name not in timeseries_metadata:
                    continue

                column_index = device_to_column[device_name]
                ts_metadata = timeseries_metadata[device_name]

                # Read analog channel data (spikeglx.Reader returns volts)
                analog_data = sr.read(
                    nsel=slice(0, n_samples),
                    csel=column_index,
                    sync=False,
                )
                # sr.read returns a 2D array; squeeze to 1D for single channel
                analog_data = np.squeeze(analog_data)

                time_series = TimeSeries(
                    data=analog_data,
                    starting_time=starting_time,
                    rate=float(sr.fs),
                    unit="volts",
                    **ts_metadata,
                )
                nwbfile.add_acquisition(time_series)
        finally:
            sr.close()
