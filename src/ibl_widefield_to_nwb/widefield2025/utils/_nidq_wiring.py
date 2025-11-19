# These functions are copied from https://github.com/h-mayorquin/IBL-to-nwb/blob/d7303e64194ad6b56fc0e51eee9d1aa71607ce62/src/ibl_to_nwb/utils/nidq_wiring.py
# create_channel_name_mapping function was modified to include 'nidq#' prefix in channel IDs


def _create_channel_name_mapping(wiring: dict | None) -> dict[str, str]:
    """
    Create a mapping from SpikeGLX channel IDs to meaningful device names.

    SpikeGLX uses technical channel identifiers (XD0, XD1, XA0, etc.) while
    the wiring.json provides semantic names (left_camera, bpod, etc.). This
    function creates a mapping between them.

    Parameters
    ----------
    wiring : dict or None
        Wiring configuration from load_nidq_wiring()

    Returns
    -------
    dict[str, str]
        Mapping from SpikeGLX channel IDs to device names.
        Example: {'XD0': 'left_camera', 'XD1': 'right_camera', 'XA0': 'bpod'}
        Returns empty dict if wiring is None.

    Notes
    -----
    Digital channel mapping:
    - P0.0 -> XD0 (bit 0 of digital port)
    - P0.1 -> XD1 (bit 1 of digital port)
    - ... up to P0.7 -> XD7

    Analog channel mapping:
    - AI0 -> XA0
    - AI1 -> XA1
    - AI2 -> XA2
    """
    if wiring is None:
        return {}

    channel_mapping = {}

    # Map digital channels (P0.0-P0.7 -> XD0-XD7)
    digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})
    for port_pin, device_name in digital_wiring.items():
        # Extract bit number from port pin (e.g., "P0.3" -> 3)
        if port_pin.startswith("P0."):
            bit_num = port_pin.split(".")[-1]
            channel_id = f"nidq#XD{bit_num}"
            channel_mapping[channel_id] = device_name

    # Map analog channels (AI0-AI2 -> XA0-XA2)
    analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})
    for analog_input, signal_name in analog_wiring.items():
        # Extract channel number from analog input (e.g., "AI0" -> 0)
        if analog_input.startswith("AI"):
            channel_num = analog_input[2:]  # Get number after 'AI'
            channel_id = f"nidq#XA{channel_num}"
            channel_mapping[channel_id] = signal_name

    return channel_mapping


def _apply_channel_name_mapping(channel_ids: list[str], channel_mapping: dict[str, str]) -> list[str]:
    """
    Apply channel name mapping to a list of channel IDs.

    Replaces technical SpikeGLX channel IDs with meaningful device names from
    the wiring configuration. If a channel ID has no mapping, it's kept as-is.

    Parameters
    ----------
    channel_ids : list[str]
        List of SpikeGLX channel IDs (e.g., ['XD0', 'XD1', 'XA0'])
    channel_mapping : dict[str, str]
        Mapping from create_channel_name_mapping()

    Returns
    -------
    list[str]
        List of device names (e.g., ['left_camera', 'right_camera', 'bpod'])
        Unmapped channels keep their original IDs.

    Examples
    --------
    >>> channel_ids = ['XD0', 'XD1', 'XA0', 'XD999']
    >>> mapping = {'XD0': 'left_camera', 'XD1': 'right_camera', 'XA0': 'bpod'}
    >>> apply_channel_name_mapping(channel_ids, mapping)
    ['left_camera', 'right_camera', 'bpod', 'XD999']
    """
    return [channel_mapping.get(ch_id, ch_id) for ch_id in channel_ids]
