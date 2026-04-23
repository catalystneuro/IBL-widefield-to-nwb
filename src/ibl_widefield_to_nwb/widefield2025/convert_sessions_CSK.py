"""Conversion script for the IBL Brain-Wide Map widefield dataset.

Publication: Findling et al., Nature 2025
DOI: 10.1038/s41586-025-09226-1
DANDI: https://dandiarchive.org/dandiset/001713

Dataset: 6 C57BL/6 wildtype mice, 52 widefield sessions.
Sync hardware: NIDQ (Neuropixels NIDQ board).

Sessions (42 total) from IBL:

['d34a502f-bd06-471f-8334-df41f785e1d9',
'3158300f-e72c-42fc-ac6c-c981615fe00f',
'2864dca1-38d8-464c-9777-f6fdfd5e63b5',
'e95a2528-709a-4590-bf60-cab0715af863',
'b95ce513-423f-4e67-aefa-5515bfe18e62',
'6ac30638-2256-4799-a0f7-f641a7b5ee50',
'a940cd7d-0882-4440-bca0-ba50f5027c15',
'e0928e11-2b86-4387-a203-80c77fab5d52',
'71f746e3-84e4-4bcc-a2df-1c261ad4acd5',
'1efa20cb-e3e9-4a28-b4f0-779e14a67d47',
'6f94a278-ee23-43bd-868f-889157db8a8d',
'8ba20ff9-d74f-42f0-b7bf-0a4c350ba53c',
'5d01d14e-aced-4465-8f8e-9a1c674f62ec',
'32c0dc1e-0b30-493c-a27e-50bfcd0378cc',
'501ba50d-73ba-44ec-8782-ef1fa6881044',
'7665dd63-7bda-430f-9425-054a2ddc3ea1',
'1fcf8413-d681-495d-8660-e73f600bab29',
'db9b17f7-6bb2-48f8-91ba-b655fc74b84a',
'12046ccd-b737-4c01-bc70-400f3b69291b',
'76448b54-0d56-469a-9c5b-6bdd3b7bce3d',
'1a507308-c63a-4e02-8f32-3239a07dc578',
'781e1046-e4f6-46e5-a727-61a667cc570f',
'8d098f4f-8067-4a17-8755-b3698e724d5d',
'e1931de1-cf7b-49af-af33-2ade15e8abe7',
'74f5c34c-f3a7-4f89-99a0-54ea388cbd9b',
'931a70ae-90ee-448e-bedb-9d41f3eda647',
'9c11a602-37e7-4973-97a4-ad461873f035',
'f7d46a15-9498-40dc-90da-fb977ce844be',
'83e77b4b-dfa0-4af9-968b-7ea0c7a0c7e4',
'484493d0-7f05-411e-a599-c9e10a1ed287',
'413a6825-2144-4a50-b3fc-cf38ddd6fd1a',
'3537d970-f515-4786-853f-23de525e110f',
'8a3a0197-b40a-449f-be55-c00b23253bbf',
'c7e4e6ad-280f-432f-ac85-9be299890d6e',
'cf63067f-e82a-4f92-93e8-c0e0eb57866d',
'5102bc6c-e8d5-494b-a227-8fb15ef983ff',
'bda2faf5-9563-4940-a80f-ce444259e47b',
'a3695e31-7165-4d62-9e99-55f78efd5580',
'be184bc8-37fb-494c-9fcf-619b10384018',
'70b6d2cf-87a5-4ec9-aaae-3536eb44896b',
'111c1762-7908-47e0-9f40-2f2ee55b6505',
'9ec2bc3b-7bf1-49ca-9136-3a0eca0ac4e3',
'b69895df-382b-4d3f-bf16-f4eff019b470',
'bf795350-d572-4a06-9ef1-999840edf0f1',
'bce316cc-263f-42fb-bf19-f8ff39ae6f5c',
'90d1e82c-c96f-496c-ad4e-ee3f02067f25',
'41431f53-69fd-4e3b-80ce-ea62e03bf9c7',
'2c3abfbf-1871-4af0-8b8a-f337ac53b3fa',
'4b8c22d7-a4d2-4924-84b0-76ec242a2f3b',
'31c9782b-da54-46d0-a257-25f06bc4e5e8',
'2cdac946-3a62-458e-9060-57466f4c6bda',
'210876d7-5465-4326-91e8-55d355ca8550',
'258b4a8b-28e3-4c18-9f86-1ea2bc0dc806',
'73918ae1-e4fd-4c18-b132-00cb555b1ad2',
'b28556ce-4ef5-4157-9c00-68a1f74ae530',
'dfe9b00e-9a20-47b0-ab1f-786f7ed827b1',
'5339812f-8b91-40ba-9d8f-a559563cc46b',
'fa9dabe2-f6bf-4522-ba33-7d7240f9b2c9',
'58b1e920-cfc8-467e-b28b-7654a55d0977',
'0c828385-6dd6-4842-a702-c5075f5f5e81',
'6dde46d9-2d48-4f01-a107-47d68d981720',
'b83033ed-c5d0-4e49-a595-0a04c48f059d',
'ba198a10-4918-41d7-8395-fee53eeb6a0a',
'034e726f-b35f-41e0-8d6c-a22cc32391fb',
'09b2c4d1-058d-4c84-9fd4-97530f85baf6',
'ff7a70f5-a2b6-4e7e-938e-e7208e0678c2',
'cf63a68b-83f2-4f93-84f1-30c02d01cd61',
'2c4a265e-3120-4f2e-b2b4-8341c778e888',
'84565bbe-fd4c-4bdb-af55-968d46a4c424',
'd62a64f4-fdc6-448b-8f2a-53ed08d645a7',
'ca316cfb-f846-4057-b33d-e651926b2b24',
'8b548e40-4bc9-41c1-a63b-d2a977b41cc0']

"""

from pathlib import Path

from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.convert_session import session_to_nwb

# =============================================================================
# Configuration
# =============================================================================

OUTPUT_DIR = Path("/Volumes/T9/data/IBL/nwbfiles/CSK")

FUNCTIONAL_WAVELENGTH_NM = 470
ISOSBESTIC_WAVELENGTH_NM = 405

STUB_TEST = False  # Set True for a quick sanity check (writes only ~100 frames)

# Dataset-specific metadata: publication, authors, species/strain/housing from the manuscript.
GENERAL_METADATA_PATH = (
    Path(__file__).parent.parent / "widefield2025" / "_metadata" / "widefield_general_metadata_CSK.yaml"
)

# =============================================================================
# Session list
# All widefield session EIDs for the IBL BWM WFI cohort (6 mice).
# TODO: replace with the complete list of EIDs from the IBL Alyx database.
# =============================================================================

EIDS = [
    # -- Mouse CSK-im-009 --
    "2864dca1-38d8-464c-9777-f6fdfd5e63b5",
    "8b548e40-4bc9-41c1-a63b-d2a977b41cc0",
    "e95a2528-709a-4590-bf60-cab0715af863",
    "3158300f-e72c-42fc-ac6c-c981615fe00f",
    # TODO: add remaining EIDs for all 6 mice
]

# =============================================================================
# ONE API
# =============================================================================

# TODO: modify with private database access kwargs
one = ONE()

# =============================================================================
# Run conversions
# =============================================================================

# TODO: add monitoring
for eid in EIDS:
    print(f"\n{'='*60}")
    print(f"Converting CSK session: {eid}")
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
