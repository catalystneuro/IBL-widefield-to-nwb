"""Conversion script for the Nrxn1α KO widefield dataset (Churchland lab, UCLA).

Publication: Davatolhagh et al., bioRxiv 2025
DOI: 10.1101/2025.09.12.675910
DANDI: https://dandiarchive.org/dandiset/001712

Dataset: 19 mice (11 Nrxn1α WT + 8 Nrxn1α KO), C57BL/6 background,
         CamKII-tTA × TRE-GCaMP6s transgenic cross.
Sync hardware: DAQ (raw_sync_data, no Neuropixels NIDQ board).
Indicator: GCaMP6s.

Sessions (17 total) from IBL (EIDs):

['81f90b18-e61c-4d32-bbce-3e0c5f33f06c',
'eaa3be3b-49fc-4aa3-9abc-30b45db5cf4c',
'e2946a6f-4157-4c38-ba7e-83c31c218ea7',
'c66ac898-82e5-4f37-826e-1e2cbd29c0f8',
'2844dbf8-db2d-49ab-a5ba-490fb18c60fe',
'76edf716-f3c5-4823-95f3-9d37ed9cbeae',
'8df7b200-e44c-4c67-82e9-2666ba05d649',
'088f44ce-926e-4a3a-808d-3f1e1a595c6f',
'b052b9d7-3bfa-4d23-b195-99cfbd3f467c',
'ba892860-149e-4bff-9961-aa6583d96661',
'a6dd4f2a-8e9f-4877-a5f7-09653ba30ac7',
'c4ef4d13-9a49-43f8-bd34-83262d9d1518',
'ba9363ab-1d37-4f14-a158-85169d905c01',
'71ceb3d4-ca68-4380-8fe7-9f63d26222f6',
'2dda7005-3392-4de5-bd65-f90263d8229f',
'257ec2b8-6e8d-4b98-99de-a232b58fde2c',
'b2aa9c2d-524e-4966-840c-f10482ae2c1a']

"""

from pathlib import Path

from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.convert_session import session_to_nwb

# =============================================================================
# Configuration
# =============================================================================

OUTPUT_DIR = Path("/Volumes/T9/data/IBL/nwbfiles/FD")

FUNCTIONAL_WAVELENGTH_NM = 470
ISOSBESTIC_WAVELENGTH_NM = 405

STUB_TEST = False  # Set True for a quick sanity check (writes only ~100 frames)

# Dataset-specific metadata: publication, authors, species/strain/housing from the manuscript.
GENERAL_METADATA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "ibl_widefield_to_nwb"
    / "widefield2025"
    / "_metadata"
    / "widefield_general_metadata_FD.yaml"
)

# =============================================================================
# Session list
# All widefield session EIDs for the Nrxn1α KO cohort.
# TODO: replace with the complete list of EIDs from the IBL Alyx database.
# =============================================================================

EIDS = [
    # -- Nrxn1α WT sessions --
    # TODO: add EIDs for all 11 WT mice
    # -- Nrxn1α KO sessions --
    "81f90b18-e61c-4d32-bbce-3e0c5f33f06c",  # known DAQ session used for testing
    # TODO: add EIDs for remaining 7 KO mice
]

# =============================================================================
# ONE API
# =============================================================================

# TODO: modify with private database access kwargs
one = ONE()

# =============================================================================
# Run conversions
# =============================================================================

for eid in EIDS:
    print(f"\n{'='*60}")
    print(f"Converting FD session: {eid}")
    print(f"{'='*60}")
    for mode in ("processed", "raw"):
        session_to_nwb(
            one=one,
            eid=eid,
            nwbfiles_folder_path=OUTPUT_DIR,
            functional_wavelength_nm=FUNCTIONAL_WAVELENGTH_NM,
            isosbestic_wavelength_nm=ISOSBESTIC_WAVELENGTH_NM,
            general_metadata_path=GENERAL_METADATA_PATH,
            mode=mode,
            stub_test=STUB_TEST,
        )
